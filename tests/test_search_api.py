import pytest
from fastapi.testclient import TestClient

from gp_claw.server import create_app


@pytest.fixture
def client(tmp_path):
    db = tmp_path / "search.db"
    app = create_app(llm=None, db_path=str(db))
    with TestClient(app) as c:
        yield c


def test_search_messages_empty(client):
    r = client.get("/search/messages", params={"q": "anything"})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 0
    assert body["items"] == []


def test_search_messages_zero_match(client):
    r = client.get("/search/messages", params={"q": "nonexistent_token"})
    assert r.status_code == 200
    assert r.json()["total"] == 0


def test_search_messages_invalid_q_empty(client):
    r = client.get("/search/messages", params={"q": ""})
    assert r.status_code == 422


def test_search_messages_role_and_room_filter(client):
    rm = client.app.state.room_manager
    store = client.app.state.message_store
    rA = rm.create(title="방A").id
    rB = rm.create(title="방B").id
    store.append(rA, "user", "alpha keyword")
    store.append(rA, "assistant", "alpha keyword")
    store.append(rB, "user", "alpha keyword")

    r = client.get("/search/messages", params={
        "q": "keyword", "room_id": [rA], "role": ["user"]
    })
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["room_id"] == rA
    assert body["items"][0]["role"] == "user"
    assert body["items"][0]["room_title"] == "방A"


def test_search_rooms_partial_case_insensitive(client):
    client.post("/rooms", json={"title": "리팩토링 회의"})
    client.post("/rooms", json={"title": "DESIGN 검토"})
    r = client.get("/search/rooms", params={"q": "design"})
    titles = [x["title"] for x in r.json()]
    assert "DESIGN 검토" in titles
    assert "리팩토링 회의" not in titles
