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

                elif data.get("type") == "user_message":
                    content = data.get("content", "")

                    if session_agent:
                        try:
                            # 스트리밍 응답
                            streamed = await _stream_agent_response(
                                session_agent, websocket,
                                {"messages": [HumanMessage(content=content)]},
                                config,
                            )

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
