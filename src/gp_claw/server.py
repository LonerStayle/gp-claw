import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from gp_claw.agent import create_agent
from gp_claw.tools import create_tool_registry
from gp_claw.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)

TOOL_TAG = "<tool_call>"
THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"


def _find_partial_match(text: str, *tags: str) -> int:
    """text 끝부분에서 tags의 부분 매치가 시작되는 위치를 반환. 없으면 len(text)."""
    flush_up_to = len(text)
    for i in range(len(text)):
        suffix = text[i:]
        if any(tag.startswith(suffix) for tag in tags):
            flush_up_to = i
            break
    return flush_up_to


async def _stream_agent_response(
    agent: Any, websocket: WebSocket, input_data: Any, config: dict
) -> bool:
    """에이전트 응답을 토큰 단위로 스트리밍.

    <think> 태그 → thinking_start/thinking_chunk/thinking_done 으로 분리.
    <tool_call> 태그 → 버퍼링 (프론트엔드에 안 보냄).
    Returns: True if any content was streamed to the client.
    """
    pending = ""
    in_thinking = False
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

        # pending 버퍼를 반복 처리 (태그 발견 시 나머지 재처리)
        changed = True
        while changed and pending:
            changed = False

            if in_thinking:
                # </think> 완전 매치
                if THINK_CLOSE in pending:
                    idx = pending.index(THINK_CLOSE)
                    if idx > 0:
                        await websocket.send_json(
                            {"type": "thinking_chunk", "content": pending[:idx]}
                        )
                    pending = pending[idx + len(THINK_CLOSE):]
                    in_thinking = False
                    await websocket.send_json({"type": "thinking_done"})
                    has_sent = True
                    changed = True  # 나머지 pending 재처리
                else:
                    # </think> 부분 매치 — 안전한 부분만 전송
                    flush_up_to = _find_partial_match(pending, THINK_CLOSE)
                    if flush_up_to > 0:
                        await websocket.send_json(
                            {"type": "thinking_chunk", "content": pending[:flush_up_to]}
                        )
                        pending = pending[flush_up_to:]

            else:
                # <think> 완전 매치
                if THINK_OPEN in pending:
                    idx = pending.index(THINK_OPEN)
                    if idx > 0:
                        await websocket.send_json(
                            {"type": "assistant_chunk", "content": pending[:idx]}
                        )
                        has_sent = True
                    pending = pending[idx + len(THINK_OPEN):]
                    in_thinking = True
                    await websocket.send_json({"type": "thinking_start"})
                    changed = True  # 나머지 pending 재처리

                # <tool_call> 완전 매치
                elif TOOL_TAG in pending:
                    idx = pending.index(TOOL_TAG)
                    if idx > 0:
                        await websocket.send_json(
                            {"type": "assistant_chunk", "content": pending[:idx]}
                        )
                        has_sent = True
                    tool_detected = True
                    break

                else:
                    # 부분 매치 — 안전한 부분만 전송
                    flush_up_to = _find_partial_match(pending, THINK_OPEN, TOOL_TAG)
                    if flush_up_to > 0:
                        await websocket.send_json(
                            {"type": "assistant_chunk", "content": pending[:flush_up_to]}
                        )
                        has_sent = True
                        pending = pending[flush_up_to:]

    # 스트리밍 종료 — 남은 pending 전송
    if not tool_detected and pending:
        if in_thinking:
            await websocket.send_json(
                {"type": "thinking_chunk", "content": pending}
            )
            await websocket.send_json({"type": "thinking_done"})
        else:
            await websocket.send_json(
                {"type": "assistant_chunk", "content": pending}
            )
        has_sent = True

    return has_sent


def create_app(
    llm: ChatOpenAI | None = None,
    registry: ToolRegistry | None = None,
    workspace_root: str | None = None,
) -> FastAPI:
    """FastAPI 애플리케이션 생성.

    Args:
        llm: LLM 인스턴스. None이면 에코 모드.
        registry: ToolRegistry. None이면 도구 없는 대화 모드.
        workspace_root: 기본 워크스페이스 경로.
    """
    app = FastAPI(title="GP Claw", version="0.3.0")
    checkpointer = MemorySaver()
    default_agent = create_agent(llm, registry=registry, checkpointer=checkpointer) if llm else None
    default_workspace = workspace_root or str(Path("~/.gp_claw/workspace").expanduser().resolve())

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        await websocket.accept()
        logger.info(f"WebSocket connected: session={session_id}")
        config = {"configurable": {"thread_id": session_id}}

        # 세션별 workspace 상태
        session_workspace = default_workspace
        session_agent = default_agent

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
                            session_agent = create_agent(llm, registry=new_registry, checkpointer=checkpointer)
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
                            while state.next:
                                interrupt_data = state.tasks[0].interrupts[0].value
                                await websocket.send_json({
                                    "type": "approval_request",
                                    **interrupt_data,
                                })

                                response = await websocket.receive_json()
                                if response.get("type") == "approval_response":
                                    decision = response.get("decision", "rejected")
                                else:
                                    decision = "rejected"

                                # resume도 스트리밍
                                streamed = await _stream_agent_response(
                                    session_agent, websocket,
                                    Command(resume=decision), config,
                                )
                                state = await session_agent.aget_state(config)

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

                            # Fallback: 스트리밍 이벤트 없으면 최종 메시지에서 가져옴
                            if not streamed:
                                final_state = await session_agent.aget_state(config)
                                msgs = final_state.values.get("messages", [])
                                if msgs:
                                    last_msg = msgs[-1]
                                    if hasattr(last_msg, "content") and last_msg.content:
                                        await websocket.send_json({
                                            "type": "assistant_chunk",
                                            "content": last_msg.content,
                                        })

                            await websocket.send_json({"type": "assistant_done"})
                        except ValueError as ve:
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
