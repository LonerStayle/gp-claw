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
    with TestClient(app) as client:
        with client.websocket_connect("/ws/test-session") as ws:
            ws.send_json({"type": "user_message", "content": "안녕"})
            data = ws.receive_json()
            assert data["type"] == "assistant_chunk"
            assert "안녕하세요" in data["content"]
            title_ev = ws.receive_json()
            assert title_ev["type"] == "room_title_updated"
            done = ws.receive_json()
            assert done["type"] == "assistant_done"


def test_ws_dual_write_to_message_store(tmp_path):
    """WS user_message 후 mirror 테이블에 user + assistant 모두 기록되는지."""
    mock_llm = MagicMock()
    mock_response = AIMessage(content="응답입니다")
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    db_path = str(tmp_path / "ws.db")
    app = create_app(llm=mock_llm, db_path=db_path)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/room-x") as ws:
            ws.send_json({"type": "user_message", "content": "hello mirror"})
            # 응답 메시지들 모두 소비 (assistant_chunk → ... → assistant_done)
            while True:
                msg = ws.receive_json()
                if msg["type"] == "assistant_done":
                    break
        # REST로 mirror 검증
        resp = client.get("/rooms/room-x/messages")
        assert resp.status_code == 200
        msgs = resp.json()
        assert any(m["type"] == "user" and m["content"] == "hello mirror" for m in msgs), \
            f"user message not mirrored: {msgs}"
