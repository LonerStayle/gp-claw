from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from gp_claw.server import create_app


def test_websocket_user_message_gets_agent_response():
    """사용자 메시지를 보내면 에이전트 응답을 받는지 확인."""
    mock_llm = MagicMock()
    mock_response = AIMessage(content="안녕하세요! 도움이 필요하신가요?")
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    app = create_app(llm=mock_llm)
    client = TestClient(app)

    with client.websocket_connect("/ws/test-session") as ws:
        ws.send_json({"type": "user_message", "content": "안녕"})
        data = ws.receive_json()
        assert data["type"] == "assistant_chunk"
        assert "안녕하세요" in data["content"]
        done = ws.receive_json()
        assert done["type"] == "assistant_done"
