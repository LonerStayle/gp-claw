"""Room 관리 REST API 테스트."""

import time

from fastapi.testclient import TestClient

from gp_claw.server import create_app


def _app():
    return create_app()


def test_list_rooms_empty():
    with TestClient(_app()) as client:
        resp = client.get("/rooms")
        assert resp.status_code == 200
        assert resp.json() == []


def test_create_room():
    with TestClient(_app()) as client:
        resp = client.post("/rooms", json={"title": "테스트 방"})
        assert resp.status_code == 201
        body = resp.json()
        assert body["title"] == "테스트 방"
        assert "id" in body
        assert "created_at" in body
        assert "updated_at" in body


def test_create_room_default_title():
    with TestClient(_app()) as client:
        resp = client.post("/rooms")
        assert resp.status_code == 201
        assert resp.json()["title"] == "새 대화"


def test_list_rooms_ordered():
    with TestClient(_app()) as client:
        ids = []
        for i in range(3):
            resp = client.post("/rooms", json={"title": f"방 {i}"})
            ids.append(resp.json()["id"])
            time.sleep(0.01)  # updated_at 차이 보장
        rooms = client.get("/rooms").json()
        # 최신순 (마지막 생성이 첫 번째)
        assert rooms[0]["id"] == ids[2]
        assert rooms[2]["id"] == ids[0]


def test_get_room():
    with TestClient(_app()) as client:
        created = client.post("/rooms", json={"title": "조회용"}).json()
        resp = client.get(f"/rooms/{created['id']}")
        assert resp.status_code == 200
        assert resp.json()["title"] == "조회용"


def test_get_room_404():
    with TestClient(_app()) as client:
        resp = client.get("/rooms/nonexistent")
        assert resp.status_code == 404


def test_update_room_title():
    with TestClient(_app()) as client:
        created = client.post("/rooms", json={"title": "원래 제목"}).json()
        resp = client.patch(f"/rooms/{created['id']}", json={"title": "변경된 제목"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "변경된 제목"


def test_update_room_404():
    with TestClient(_app()) as client:
        resp = client.patch("/rooms/nonexistent", json={"title": "변경"})
        assert resp.status_code == 404


def test_delete_room():
    with TestClient(_app()) as client:
        created = client.post("/rooms", json={"title": "삭제용"}).json()
        resp = client.delete(f"/rooms/{created['id']}")
        assert resp.status_code == 204
        # 삭제 후 조회
        resp = client.get(f"/rooms/{created['id']}")
        assert resp.status_code == 404


def test_delete_room_404():
    with TestClient(_app()) as client:
        resp = client.delete("/rooms/nonexistent")
        assert resp.status_code == 404


def test_get_messages_empty():
    with TestClient(_app()) as client:
        created = client.post("/rooms", json={"title": "빈 대화"}).json()
        resp = client.get(f"/rooms/{created['id']}/messages")
        assert resp.status_code == 200
        assert resp.json() == []


def test_get_messages_room_not_found():
    with TestClient(_app()) as client:
        resp = client.get("/rooms/nonexistent/messages")
        assert resp.status_code == 404
