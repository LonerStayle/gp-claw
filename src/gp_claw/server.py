import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from gp_claw.agent import create_agent
from gp_claw.tools import create_tool_registry
from gp_claw.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


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
                            result = await session_agent.ainvoke(
                                {"messages": [HumanMessage(content=content)]},
                                config,
                            )

                            # Phase 2C: interrupt 처리 (approval 루프)
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

                                from langgraph.types import Command
                                result = await session_agent.ainvoke(
                                    Command(resume=decision), config,
                                )
                                state = await session_agent.aget_state(config)

                            last_message = result["messages"][-1]
                            if hasattr(last_message, "content") and last_message.content:
                                await websocket.send_json({
                                    "type": "assistant_message",
                                    "content": last_message.content,
                                })
                        except Exception as e:
                            logger.error(f"Agent error: {e}", exc_info=True)
                            await websocket.send_json({
                                "type": "error",
                                "content": f"LLM 오류: {e}",
                            })
                    else:
                        await websocket.send_json({
                            "type": "assistant_message",
                            "content": f"[에코] {content}",
                        })

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
