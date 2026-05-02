import logging
import re as _re
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

import aiosqlite
from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command
from pydantic import BaseModel

from gp_claw.agent import create_agent
from gp_claw.messages import MessageStore
from gp_claw.rooms import RoomManager
from gp_claw.tools import create_tool_registry
from gp_claw.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

TOOL_TAG = "<tool_call>"


async def _stream_agent_response(
    agent: Any, websocket: WebSocket, input_data: Any, config: dict
) -> bool:
    """에이전트 응답을 토큰 단위로 스트리밍.

    <tool_call> 태그가 감지되면 스트리밍을 중단하고 버퍼링합니다.
    Returns: True if any content was streamed to the client.
    """
    pending = ""
    tool_detected = False
    has_sent = False

    async for event in agent.astream_events(input_data, config, version="v2"):
        if event["event"] != "on_chat_model_stream":
            continue
        chunk = event["data"]["chunk"]
        if not hasattr(chunk, "content") or not chunk.content:
            continue

        if tool_detected:
            continue

        pending += chunk.content

        # 완전한 <tool_call> 태그 발견
        if TOOL_TAG in pending:
            idx = pending.index(TOOL_TAG)
            if idx > 0:
                await websocket.send_json(
                    {"type": "assistant_chunk", "content": pending[:idx]}
                )
                has_sent = True
            tool_detected = True
            continue

        # <tool_call> 의 부분 매치 확인 — 매치 가능한 부분은 보류
        flush_up_to = len(pending)
        for i in range(len(pending)):
            if TOOL_TAG.startswith(pending[i:]):
                flush_up_to = i
                break

        if flush_up_to > 0:
            await websocket.send_json(
                {"type": "assistant_chunk", "content": pending[:flush_up_to]}
            )
            has_sent = True
            pending = pending[flush_up_to:]

    # 스트리밍 종료 — 남은 pending 전송
    if not tool_detected and pending:
        await websocket.send_json(
            {"type": "assistant_chunk", "content": pending}
        )
        has_sent = True

    return has_sent


def create_app(
    llm: ChatOpenAI | None = None,
    registry: ToolRegistry | None = None,
    workspace_root: str | None = None,
    db_path: str = ":memory:",
) -> FastAPI:
    """FastAPI 애플리케이션 생성.

    Args:
        llm: LLM 인스턴스. None이면 에코 모드.
        registry: ToolRegistry. None이면 도구 없는 대화 모드.
        workspace_root: 기본 워크스페이스 경로.
        db_path: SQLite DB 경로. 기본값 ":memory:".
    """
    # Mutable holders — populated in lifespan (AsyncSqliteSaver needs event loop)
    _checkpointer = [None]
    _agent = [None]
    _msg_store = [None]  # type: ignore[var-annotated]

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        conn = await aiosqlite.connect(db_path)
        await conn.execute("PRAGMA journal_mode=WAL")
        _checkpointer[0] = AsyncSqliteSaver(conn)
        await _checkpointer[0].setup()
        _agent[0] = create_agent(llm, registry=registry, checkpointer=_checkpointer[0]) if llm else None
        _msg_store[0] = MessageStore(db_path)  # 같은 DB 파일 사용 — 별도 테이블
        _app.state.message_store = _msg_store[0]
        _app.state.room_manager = room_manager
        yield
        _msg_store[0].close()
        await conn.close()

    app = FastAPI(title="GP Claw", version="0.3.0", lifespan=lifespan)
    default_workspace = workspace_root or str(Path("~/.gp_claw/workspace").expanduser().resolve())
    room_manager = RoomManager(db_path)

    # --- Pydantic models for request bodies ---
    class RoomTitleBody(BaseModel):
        title: str = "새 대화"

    # --- Health ---
    @app.get("/health")
    async def health():
        return {"status": "ok"}

    # --- Room REST API ---
    @app.get("/rooms")
    async def list_rooms():
        return [asdict(r) for r in room_manager.list_all()]

    @app.post("/rooms", status_code=201)
    async def create_room(body: RoomTitleBody | None = None):
        title = body.title if body else "새 대화"
        room = room_manager.create(title=title)
        return asdict(room)

    @app.get("/rooms/{room_id}")
    async def get_room(room_id: str):
        room = room_manager.get(room_id)
        if not room:
            return JSONResponse(status_code=404, content={"detail": "Room not found"})
        return asdict(room)

    @app.patch("/rooms/{room_id}")
    async def update_room(room_id: str, body: RoomTitleBody):
        room = room_manager.update_title(room_id, body.title)
        if not room:
            return JSONResponse(status_code=404, content={"detail": "Room not found"})
        return asdict(room)

    @app.delete("/rooms/{room_id}", status_code=204)
    async def delete_room(room_id: str):
        if not room_manager.delete(room_id):
            return JSONResponse(status_code=404, content={"detail": "Room not found"})
        # 체크포인터 데이터도 정리
        try:
            await _checkpointer[0].adelete_thread(room_id)
        except Exception:
            pass

    @app.get("/rooms/{room_id}/messages")
    async def get_room_messages(room_id: str):
        room = room_manager.get(room_id)
        if not room:
            return JSONResponse(status_code=404, content={"detail": "Room not found"})
        if not _msg_store[0]:
            return []
        return _msg_store[0].list_by_room(room_id)

    # --- Search REST API ---
    @app.get("/search/messages")
    async def search_messages(
        q: str = Query(..., min_length=1),
        room_id: list[str] | None = Query(default=None),
        role: list[str] | None = Query(default=None),
        date_from: str | None = Query(default=None, alias="from"),
        date_to: str | None = Query(default=None, alias="to"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        if not _msg_store[0]:
            return {"total": 0, "items": []}
        result = _msg_store[0].search(
            q=q, room_ids=room_id, roles=role,
            date_from=date_from, date_to=date_to,
            limit=limit, offset=offset,
        )
        # 결과 항목에 room_title 채워넣기 (FR-3)
        titles = {r.id: r.title for r in room_manager.list_all()}
        for it in result["items"]:
            it["room_title"] = titles.get(it["room_id"], "")
        return result

    @app.get("/search/rooms")
    async def search_rooms(q: str = Query(default="")):
        rooms = room_manager.list_all()
        if not q:
            return [asdict(r) for r in rooms]
        ql = q.lower()
        return [asdict(r) for r in rooms if ql in r.title.lower()]

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        await websocket.accept()
        logger.info(f"WebSocket connected: session={session_id}")

        config = {"configurable": {"thread_id": session_id}}

        async def _recover_thread():
            """스트리밍 에러 시 오염된 체크포인트를 제거하고 대화 히스토리를 복원."""
            if not session_agent:
                return
            # 1) 오염 직전까지의 정상 메시지 저장
            try:
                state = await session_agent.aget_state(config)
                saved = list(state.values.get("messages", []))
                # 마지막 HumanMessage(에러 유발)와 그 뒤 불완전 응답 제거
                while saved and not isinstance(saved[-1], HumanMessage):
                    saved.pop()
                if saved:
                    saved.pop()  # 에러 유발 HumanMessage도 제거
            except Exception:
                saved = []
            # 2) 오염된 체크포인트 전체 삭제
            thread_id = config["configurable"]["thread_id"]
            try:
                await _checkpointer[0].adelete_thread(thread_id)
            except Exception:
                pass
            # 3) 정상 메시지 복원
            if saved:
                try:
                    await session_agent.aupdate_state(config, {"messages": saved})
                except Exception:
                    pass
            logger.warning(
                f"Thread recovered: session={session_id}, "
                f"preserved {len(saved)} messages"
            )

        # 세션별 workspace 상태
        session_workspace = default_workspace
        session_agent = _agent[0]

        try:
            while True:
                data = await websocket.receive_json()

                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

                elif data.get("type") == "set_workspace":
                    raw_path = data.get("path", "")
                    new_path = Path(raw_path).expanduser().resolve()
                    if not new_path.exists():
                        await websocket.send_json({
                            "type": "workspace_error",
                            "content": f"경로를 찾을 수 없습니다: {raw_path}",
                        })
                    elif not new_path.is_dir():
                        await websocket.send_json({
                            "type": "workspace_error",
                            "content": f"디렉토리가 아닙니다: {raw_path}",
                        })
                    else:
                        session_workspace = str(new_path)
                        if llm:
                            new_registry = create_tool_registry(session_workspace)
                            session_agent = create_agent(llm, registry=new_registry, checkpointer=_checkpointer[0])
                        display = str(new_path).replace(str(Path.home()), "~")
                        logger.info(f"Workspace changed: session={session_id}, path={session_workspace}")
                        await websocket.send_json({
                            "type": "workspace_changed",
                            "path": session_workspace,
                            "display": display,
                        })

                elif data.get("type") == "open_file":
                    from gp_claw.security import validate_path, SecurityViolation
                    from gp_claw.tools.office_file import _open_with_os

                    raw_path = data.get("path", "")
                    try:
                        validated = validate_path(raw_path, session_workspace)
                        if not validated.exists():
                            await websocket.send_json({
                                "type": "error",
                                "content": f"파일을 찾을 수 없습니다: {raw_path}",
                            })
                        else:
                            _open_with_os(str(validated))
                            await websocket.send_json({
                                "type": "file_opened",
                                "path": str(validated),
                                "filename": validated.name,
                            })
                    except SecurityViolation as e:
                        await websocket.send_json({
                            "type": "error",
                            "content": str(e),
                        })

                elif data.get("type") == "user_message":
                    content = data.get("content", "")

                    # Room 자동 생성/갱신
                    if not room_manager.get(session_id):
                        room_manager.create(room_id=session_id)
                    room_manager.touch(session_id)

                    # Mirror write — user 메시지 (R-1: try/except로 본 흐름 보호)
                    try:
                        if _msg_store[0]:
                            _msg_store[0].append(room_id=session_id, role="user", content=content)
                    except Exception as e:
                        logger.warning(f"MessageStore.append(user) failed: {e}")

                    is_first_message = room_manager.get(session_id).title == "새 대화"

                    if session_agent:
                        try:
                            # 스트리밍 응답 (빈 스트림 시 1회 재시도)
                            input_data = {"messages": [HumanMessage(content=content)]}
                            try:
                                streamed = await _stream_agent_response(
                                    session_agent, websocket, input_data, config,
                                )
                            except ValueError as ve:
                                if "No generations found in stream" in str(ve):
                                    logger.warning("Empty stream from LLM, retrying once...")
                                    await websocket.send_json({
                                        "type": "assistant_chunk",
                                        "content": "서버가 준비 중입니다. 재시도 중...\n\n",
                                    })
                                    streamed = await _stream_agent_response(
                                        session_agent, websocket, input_data, config,
                                    )
                                else:
                                    raise

                            # interrupt 처리 (approval 루프)
                            state = await session_agent.aget_state(config)
                            try:
                                while state.next:
                                    interrupt_data = state.tasks[0].interrupts[0].value
                                    await websocket.send_json({
                                        "type": "approval_request",
                                        **interrupt_data,
                                    })

                                    # 승인 응답 대기 (approval_response 외 모든 메시지 무시)
                                    decision = "rejected"
                                    while True:
                                        response = await websocket.receive_json()
                                        if response.get("type") == "approval_response":
                                            decision = response.get("decision", "rejected")
                                            break
                                        if response.get("type") == "ping":
                                            await websocket.send_json({"type": "pong"})
                                        # 그 외 메시지는 무시하고 계속 대기

                                    # resume도 스트리밍
                                    streamed = await _stream_agent_response(
                                        session_agent, websocket,
                                        Command(resume=decision), config,
                                    )
                                    state = await session_agent.aget_state(config)
                            except Exception as loop_err:
                                await _recover_thread()
                                raise loop_err

                            # 도구 실행 결과에서 파일 생성 감지 → file_created 전송
                            final_state = await session_agent.aget_state(config)
                            all_msgs = final_state.values.get("messages", [])
                            # 마지막 HumanMessage 이후의 메시지만 스캔
                            recent_msgs = []
                            for i in range(len(all_msgs) - 1, -1, -1):
                                if isinstance(all_msgs[i], HumanMessage):
                                    recent_msgs = all_msgs[i + 1:]
                                    break
                            for msg in recent_msgs:
                                if hasattr(msg, "name") and hasattr(msg, "content"):
                                    try:
                                        import json as _json
                                        result = _json.loads(msg.content) if isinstance(msg.content, str) else msg.content
                                        if isinstance(result, dict) and result.get("action") == "created":
                                            await websocket.send_json({
                                                "type": "file_created",
                                                "path": result.get("path", ""),
                                                "filename": Path(result.get("path", "")).name,
                                                "size_bytes": result.get("size_bytes", 0),
                                            })
                                    except (ValueError, TypeError):
                                        pass

                            # Mirror write — assistant/tool 메시지들 (R-1)
                            try:
                                if _msg_store[0]:
                                    for m in recent_msgs:
                                        role = None
                                        if isinstance(m, AIMessage):
                                            role = "assistant"
                                        elif hasattr(m, "type") and m.type == "tool":
                                            role = "tool"
                                        if role and getattr(m, "content", None):
                                            _msg_store[0].append(
                                                room_id=session_id,
                                                role=role,
                                                content=str(m.content),
                                            )
                            except Exception as e:
                                logger.warning(f"MessageStore.append(assistant/tool) failed: {e}")

                            # Fallback: 스트리밍 이벤트 없으면 최종 메시지에서 가져옴
                            if not streamed:
                                final_state = await session_agent.aget_state(config)
                                msgs = final_state.values.get("messages", [])
                                if msgs:
                                    last_msg = msgs[-1]
                                    if hasattr(last_msg, "content") and last_msg.content:
                                        # <tool_call> 태그 제거 후 전송
                                        import re as _re
                                        fallback_text = _re.sub(
                                            r"</?tool_call>.*", "", last_msg.content, flags=_re.DOTALL
                                        ).strip()
                                        if fallback_text:
                                            await websocket.send_json({
                                                "type": "assistant_chunk",
                                                "content": fallback_text,
                                            })

                            # 자동 제목: 첫 메시지 앞 30자
                            if is_first_message:
                                auto_title = content[:30].strip() or "새 대화"
                                room_manager.update_title(session_id, auto_title)
                                await websocket.send_json({
                                    "type": "room_title_updated",
                                    "room_id": session_id,
                                    "title": auto_title,
                                })

                            await websocket.send_json({"type": "assistant_done"})
                        except ValueError as ve:
                            await _recover_thread()
                            if "No generations found in stream" in str(ve):
                                logger.warning(f"Empty LLM stream: {ve}")
                                await websocket.send_json({
                                    "type": "error",
                                    "content": "AI 서버가 응답하지 않았습니다. 잠시 후 다시 시도해 주세요. (RunPod 콜드 스타트일 수 있습니다)",
                                })
                            else:
                                logger.error(f"Agent error: {ve}", exc_info=True)
                                await websocket.send_json({
                                    "type": "error",
                                    "content": f"LLM 오류: {ve}",
                                })
                        except Exception as e:
                            await _recover_thread()
                            logger.error(f"Agent error: {e}", exc_info=True)
                            await websocket.send_json({
                                "type": "error",
                                "content": f"LLM 오류: {e}",
                            })
                    else:
                        await websocket.send_json({
                            "type": "assistant_chunk",
                            "content": f"[에코] {content}",
                        })
                        # 에코 모드에서도 자동 제목
                        if is_first_message:
                            auto_title = content[:30].strip() or "새 대화"
                            room_manager.update_title(session_id, auto_title)
                            await websocket.send_json({
                                "type": "room_title_updated",
                                "room_id": session_id,
                                "title": auto_title,
                            })
                        await websocket.send_json({"type": "assistant_done"})

                else:
                    await websocket.send_json({
                        "type": "error",
                        "content": f"알 수 없는 메시지 타입: {data.get('type')}",
                    })

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: session={session_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            await websocket.close(code=1011, reason=str(e))

    return app
