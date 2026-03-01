from fastapi.testclient import TestClient

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
