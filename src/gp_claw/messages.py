"""Mirror store for searchable messages — SQLite 기반."""

import re
import sqlite3
from datetime import datetime, timezone


_TOOL_TAG_RE = re.compile(r"</?tool_call>.*", re.DOTALL)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean(text: str) -> str:
    return _TOOL_TAG_RE.sub("", text or "").strip()


class MessageStore:
    """Mirror table for full-text-ish keyword search across all rooms."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._create_schema()

    def _create_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                room_id     TEXT    NOT NULL,
                role        TEXT    NOT NULL,
                content     TEXT    NOT NULL,
                created_at  TEXT    NOT NULL,
                seq         INTEGER NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_created_at ON messages(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_room_id    ON messages(room_id);
            CREATE INDEX IF NOT EXISTS idx_messages_role       ON messages(role);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_room_seq ON messages(room_id, seq);
        """)
        self._conn.commit()

    def append(
        self,
        room_id: str,
        role: str,
        content: str,
        created_at: str | None = None,
        _attempt: int = 0,
    ) -> int | None:
        # ⚠️ RISK(side-effect): <tool_call> 정제 — by R-5
        cleaned = _clean(content)
        if not cleaned:
            return None
        ts = created_at or _now_iso()
        # ⚠️ RISK(race): seq를 트랜잭션 내에서 MAX+1 — by R-2
        try:
            with self._conn:
                row = self._conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) AS m FROM messages WHERE room_id = ?",
                    (room_id,),
                ).fetchone()
                next_seq = (row["m"] or 0) + 1
                cur = self._conn.execute(
                    """INSERT INTO messages (room_id, role, content, created_at, seq)
                       VALUES (?, ?, ?, ?, ?)""",
                    (room_id, role, cleaned, ts, next_seq),
                )
                return cur.lastrowid
        except sqlite3.IntegrityError:
            # seq 충돌 시 1회 재시도 (단일 사용자 가정 — 거의 발생 안함)
            if _attempt >= 1:
                raise
            return self.append(room_id, role, content, created_at, _attempt=_attempt + 1)

    def search(
        self,
        q: str,
        room_ids: list[str] | None = None,
        roles: list[str] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict:
        clauses = ["LOWER(content) LIKE ?"]
        params: list = [f"%{q.lower()}%"]
        if room_ids:
            placeholders = ",".join(["?"] * len(room_ids))
            clauses.append(f"room_id IN ({placeholders})")
            params.extend(room_ids)
        if roles:
            placeholders = ",".join(["?"] * len(roles))
            clauses.append(f"role IN ({placeholders})")
            params.extend(roles)
        if date_from:
            clauses.append("created_at >= ?")
            params.append(date_from)
        if date_to:
            clauses.append("created_at <= ?")
            params.append(date_to)
        where = " AND ".join(clauses)
        total = self._conn.execute(
            f"SELECT COUNT(*) AS c FROM messages WHERE {where}", params
        ).fetchone()["c"]
        rows = self._conn.execute(
            f"""SELECT id, room_id, role, content, created_at
                FROM messages WHERE {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        items = [self._row_to_item(r, q) for r in rows]
        return {"total": total, "items": items}

    @staticmethod
    def _row_to_item(row: sqlite3.Row, q: str) -> dict:
        content: str = row["content"]
        lower = content.lower()
        ql = q.lower()
        idx = lower.find(ql)
        if idx >= 0:
            start = max(0, idx - 50)
            end = min(len(content), idx + len(q) + 50)
            snippet = ("…" if start > 0 else "") + content[start:end] + ("…" if end < len(content) else "")
            offsets = [[idx, idx + len(q)]]
        else:
            snippet = content[:120]
            offsets = []
        return {
            "id": row["id"],
            "room_id": row["room_id"],
            "role": row["role"],
            "content": content,
            "snippet": snippet,
            "match_offsets": offsets,
            "created_at": row["created_at"],
        }

    def list_by_room(self, room_id: str) -> list[dict]:
        rows = self._conn.execute(
            """SELECT id, role, content, created_at FROM messages
               WHERE room_id = ? ORDER BY seq ASC""",
            (room_id,),
        ).fetchall()
        return [
            {"id": r["id"], "type": r["role"], "content": r["content"],
             "created_at": r["created_at"]}
            for r in rows
        ]

    def close(self) -> None:
        self._conn.close()
