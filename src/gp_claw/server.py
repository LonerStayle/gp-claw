import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from gp_claw.agent import create_agent
from gp_claw.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def create_app(
    llm: ChatOpenAI | None = None,
    registry: ToolRegistry | None = None,
) -> FastAPI:
    """FastAPI 애플리케이션 생성.

    Args:
        llm: LLM 인스턴스. None이면 에코 모드.
        registry: ToolRegistry. None이면 도구 없는 대화 모드.
    """
    app = FastAPI(title="GP Claw", version="0.2.0")
    checkpointer = MemorySaver()
    agent = create_agent(llm, registry=registry, checkpointer=checkpointer) if llm else None

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        await websocket.accept()
        logger.info(f"WebSocket connected: session={session_id}")
        config = {"configurable": {"thread_id": session_id}}

        try:
            while True:
                data = await websocket.receive_json()

                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

                elif data.get("type") == "user_message":
                    content = data.get("content", "")

                    if agent:
                        try:
                            result = await agent.ainvoke(
                                {"messages": [HumanMessage(content=content)]},
                                config,
                            )

                            # Phase 2C: interrupt 처리 (approval 루프)
                            state = await agent.aget_state(config)
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
                                result = await agent.ainvoke(
                                    Command(resume=decision), config,
                                )
                                state = await agent.aget_state(config)

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
