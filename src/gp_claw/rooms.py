"""Room 메타데이터 매니저 — 인메모리 dict 기반."""

from dataclasses import dataclass, field
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
    """인메모리 Room CRUD. Room ID = LangGraph thread_id."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}

    def create(self, title: str = "새 대화", room_id: str | None = None) -> Room:
        rid = room_id or uuid4().hex
        now = _now_iso()
        room = Room(id=rid, title=title, created_at=now, updated_at=now)
        self._rooms[rid] = room
        return room

    def list_all(self) -> list[Room]:
        return sorted(self._rooms.values(), key=lambda r: r.updated_at, reverse=True)

    def get(self, room_id: str) -> Room | None:
        return self._rooms.get(room_id)

    def update_title(self, room_id: str, title: str) -> Room | None:
        room = self._rooms.get(room_id)
        if room is None:
            return None
        room.title = title
        room.updated_at = _now_iso()
        return room

    def touch(self, room_id: str) -> None:
        room = self._rooms.get(room_id)
        if room:
            room.updated_at = _now_iso()

    def delete(self, room_id: str) -> bool:
        return self._rooms.pop(room_id, None) is not None
