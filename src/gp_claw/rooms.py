"""Room 메타데이터 매니저 — SQLite 기반."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Room:
    id: str
    title: str
    created_at: str
    updated_at: str


class RoomManager:
    """SQLite Room CRUD. Room ID = LangGraph thread_id."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_table()

    def _create_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        self._conn.commit()

    def _row_to_room(self, row: sqlite3.Row) -> Room:
        return Room(id=row["id"], title=row["title"],
                    created_at=row["created_at"], updated_at=row["updated_at"])

    def create(self, title: str = "새 대화", room_id: str | None = None) -> Room:
        rid = room_id or uuid4().hex
        now = _now_iso()
        self._conn.execute(
            "INSERT INTO rooms (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (rid, title, now, now),
        )
        self._conn.commit()
        return Room(id=rid, title=title, created_at=now, updated_at=now)

    def list_all(self) -> list[Room]:
        rows = self._conn.execute(
            "SELECT * FROM rooms ORDER BY updated_at DESC"
        ).fetchall()
        return [self._row_to_room(r) for r in rows]

    def get(self, room_id: str) -> Room | None:
        row = self._conn.execute(
            "SELECT * FROM rooms WHERE id = ?", (room_id,)
        ).fetchone()
        return self._row_to_room(row) if row else None

    def update_title(self, room_id: str, title: str) -> Room | None:
        now = _now_iso()
        cur = self._conn.execute(
            "UPDATE rooms SET title = ?, updated_at = ? WHERE id = ?",
            (title, now, room_id),
        )
        self._conn.commit()
        if cur.rowcount == 0:
            return None
        return self.get(room_id)

    def touch(self, room_id: str) -> None:
        now = _now_iso()
        self._conn.execute(
            "UPDATE rooms SET updated_at = ? WHERE id = ?", (now, room_id)
        )
        self._conn.commit()

    def delete(self, room_id: str) -> bool:
        cur = self._conn.execute("DELETE FROM rooms WHERE id = ?", (room_id,))
        self._conn.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        self._conn.close()
