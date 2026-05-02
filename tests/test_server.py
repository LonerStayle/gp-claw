import pytest
from fastapi.testclient import TestClient

from gp_claw.messages import MessageStore
from gp_claw.server import create_app


def test_health_endpoint():
    """헬스체크 엔드포인트가 동작하는지 확인."""
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_websocket_connect():
    """WebSocket 연결이 수립되는지 확인."""
    app = create_app()
    with TestClient(app) as client:
        with client.websocket_connect("/ws/test-session") as ws:
            ws.send_json({"type": "ping"})
            data = ws.receive_json()
            assert data["type"] == "pong"


@pytest.fixture
def client_with_room_and_messages(tmp_path):
    """Room 생성 + MessageStore에 메시지 직접 inject한 TestClient.

    Task 3의 app.state.message_store 노출 없이도 동작하도록 같은 DB 파일에
    별도 MessageStore를 열어서 직접 append한다.
    """
    db_path = str(tmp_path / "server.db")
    app = create_app(llm=None, db_path=db_path)
    with TestClient(app) as client:
        # Room 생성
        r = client.post("/rooms", json={"title": "test"})
        room_id = r.json()["id"]
        # 같은 DB에 별도 MessageStore 열어서 메시지 직접 inject
        # (lifespan의 _msg_store와 동일한 DB 파일을 공유; SQLite WAL이라 안전)
        store = MessageStore(db_path)
        store.append(room_id=room_id, role="user", content="첫번째 메시지")
        store.append(room_id=room_id, role="assistant", content="두번째 메시지")
        store.close()
        yield client, room_id


def test_get_room_messages_returns_id_field(client_with_room_and_messages):
    """R-7 회귀: id 필드 존재 + 메시지 순서대로 단조 증가."""
    client, room_id = client_with_room_and_messages
    r = client.get(f"/rooms/{room_id}/messages")
    assert r.status_code == 200
    msgs = r.json()
    assert len(msgs) >= 2
    assert all("id" in m for m in msgs)
    ids = [m["id"] for m in msgs]
    assert ids == sorted(ids), f"id가 단조 증가하지 않음: {ids}"
