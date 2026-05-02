"""기존 LangGraph 체크포인트에서 messages 테이블로 1회 마이그레이션.

Usage:
    python -m scripts.backfill_messages              # settings.db_path 자동 사용
    python -m scripts.backfill_messages <db_path>    # 명시적 경로
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

# editable install이 main repo를 가리키고 있을 때 worktree의 src/를 우선 적용
_SRC = Path(__file__).resolve().parent.parent / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import aiosqlite
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from gp_claw.messages import MessageStore
from gp_claw.rooms import RoomManager


def _role_of(msg) -> str | None:
    if isinstance(msg, HumanMessage):
        return "user"
    if isinstance(msg, AIMessage):
        return "assistant"
    if isinstance(msg, ToolMessage):
        return "tool"
    if isinstance(msg, SystemMessage):
        return "system"
    return None


async def backfill(db_path: str) -> int:
    """모든 방을 순회하며 메시지를 messages 테이블에 적재. 멱등.

    각 메시지의 `created_at`은 방의 `updated_at`을 사용 — 체크포인트에 메시지별
    timestamp가 없기 때문. 동일 방의 메시지들은 같은 timestamp를 갖되 `seq`
    컬럼으로 순서가 보존된다.

    Returns: appended row count.
    """
    rm = RoomManager(db_path)
    rooms = rm.list_all()
    rm.close()
    if not rooms:
        print("[backfill] 방이 없습니다 — 적재할 데이터 없음")
        return 0

    store = MessageStore(db_path)
    # 기존 row 정리(멱등 보장: 부분 적재 후 재실행 케이스 대비)
    deleted = store._conn.execute("DELETE FROM messages").rowcount
    store._conn.commit()
    if deleted:
        print(f"[backfill] 기존 mirror row {deleted}개 정리")

    appended = 0
    skipped_rooms = 0
    conn = await aiosqlite.connect(db_path)
    try:
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        for i, room in enumerate(rooms, 1):
            try:
                cps = saver.alist({"configurable": {"thread_id": room.id}})
                latest = None
                try:
                    async for cp in cps:
                        latest = cp
                        break
                finally:
                    # async generator 명시적 close — connection cleanup 시 race 방지
                    await cps.aclose()
                if latest is None:
                    skipped_rooms += 1
                    continue
                state_msgs = latest.checkpoint.get("channel_values", {}).get("messages", [])
                ts = room.updated_at or datetime.now(timezone.utc).isoformat()
                room_count = 0
                for m in state_msgs:
                    role = _role_of(m)
                    if not role:
                        continue
                    rid = store.append(
                        room_id=room.id,
                        role=role,
                        content=getattr(m, "content", "") or "",
                        created_at=ts,
                    )
                    if rid is not None:
                        appended += 1
                        room_count += 1
                print(
                    f"[backfill] ({i}/{len(rooms)}) {room.title!r} → {room_count}개"
                )
            except Exception as e:
                skipped_rooms += 1
                print(f"[backfill] room={room.id} failed: {e}", file=sys.stderr)
    finally:
        await conn.close()
        store.close()

    print(
        f"[backfill] 완료: 총 {appended}개 메시지 적재 "
        f"({len(rooms) - skipped_rooms}/{len(rooms)} 방 처리)"
    )
    return appended


def _resolve_db_path() -> str:
    """CLI 인자 또는 Settings 에서 db_path 결정."""
    if len(sys.argv) >= 2:
        return sys.argv[1]
    try:
        from gp_claw.config import Settings
        s = Settings()  # type: ignore[call-arg]
        return str(s.db_path.expanduser())
    except Exception as e:
        print(
            "DB 경로를 결정할 수 없습니다.\n"
            "usage: python -m scripts.backfill_messages [db_path]\n"
            f"detail: {e}",
            file=sys.stderr,
        )
        sys.exit(1)


def _main() -> None:
    db_path = _resolve_db_path()
    print(f"[backfill] 대상 DB: {db_path}")
    asyncio.run(backfill(db_path))


if __name__ == "__main__":
    _main()
