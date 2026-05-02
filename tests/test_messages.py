import sqlite3
import pytest
from gp_claw.messages import MessageStore


@pytest.fixture
def store(tmp_path):
    db = tmp_path / "test.db"
    s = MessageStore(str(db))
    yield s
    s.close()


def test_empty_search_returns_zero(store):
    result = store.search(q="hello")
    assert result["total"] == 0
    assert result["items"] == []


def test_append_then_search_finds_match(store):
    store.append(room_id="r1", role="user", content="hello world")
    result = store.search(q="hello")
    assert result["total"] == 1
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["room_id"] == "r1"
    assert item["role"] == "user"
    assert item["content"] == "hello world"
    assert "hello" in item["snippet"].lower()
    assert isinstance(item["match_offsets"], list)
    assert item["match_offsets"][0] == [0, 5]


def test_role_filter(store):
    store.append("r1", "user", "alpha")
    store.append("r1", "assistant", "alpha")
    res = store.search(q="alpha", roles=["user"])
    assert res["total"] == 1
    assert res["items"][0]["role"] == "user"


def test_room_filter(store):
    store.append("r1", "user", "x")
    store.append("r2", "user", "x")
    res = store.search(q="x", room_ids=["r2"])
    assert res["total"] == 1
    assert res["items"][0]["room_id"] == "r2"


def test_date_range(store):
    store.append("r1", "user", "old", created_at="2026-01-01T00:00:00+00:00")
    store.append("r1", "user", "new", created_at="2026-05-01T00:00:00+00:00")
    res = store.search(q="", date_from="2026-04-01T00:00:00+00:00")
    assert res["total"] == 1
    assert res["items"][0]["content"] == "new"


def test_tool_call_stripped(store):
    rid = store.append("r1", "assistant", "answer\n<tool_call>{...}</tool_call>")
    rows = store._conn.execute("SELECT content FROM messages WHERE id=?", (rid,)).fetchall()
    assert rows[0]["content"] == "answer"


def test_empty_assistant_skipped(store):
    rid = store.append("r1", "assistant", "<tool_call>x</tool_call>")
    assert rid is None


def test_case_insensitive_partial(store):
    store.append("r1", "user", "Reactive Programming")
    res = store.search(q="REACT")
    assert res["total"] == 1


def test_pagination(store):
    for i in range(5):
        store.append("r1", "user", f"item {i}", created_at=f"2026-05-0{i+1}T00:00:00+00:00")
    page1 = store.search(q="item", limit=2, offset=0)
    page2 = store.search(q="item", limit=2, offset=2)
    assert page1["total"] == 5
    assert page2["total"] == 5
    assert len(page1["items"]) == 2 and len(page2["items"]) == 2
    assert page1["items"][0]["content"] == "item 4"  # latest first
    assert page2["items"][0]["content"] == "item 2"


def test_persistent_integrity_error_is_bounded(store, monkeypatch):
    """Persistent IntegrityError must raise after 1 retry, not recurse."""
    call_count = {"n": 0}
    real_conn = store._conn

    class _ProxyConn:
        """Wraps the real sqlite3.Connection but raises on INSERT INTO messages."""

        def execute(self, sql, *args, **kwargs):
            if "INSERT INTO messages" in sql:
                call_count["n"] += 1
                raise sqlite3.IntegrityError("simulated persistent failure")
            return real_conn.execute(sql, *args, **kwargs)

        def __enter__(self):
            return real_conn.__enter__()

        def __exit__(self, *args):
            return real_conn.__exit__(*args)

        def __getattr__(self, name):
            return getattr(real_conn, name)

    monkeypatch.setattr(store, "_conn", _ProxyConn())
    with pytest.raises(sqlite3.IntegrityError):
        store.append("r1", "user", "test")
    # 1 initial attempt + 1 retry = 2 INSERT attempts max
    assert call_count["n"] == 2, f"expected 2 INSERT attempts, got {call_count['n']}"
