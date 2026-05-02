"""기존 LangGraph 체크포인트에서 messages 테이블로 1회 마이그레이션."""

import asyncio
import sys
from datetime import datetime, timezone

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

    Returns: appended row count.
    """
    rm = RoomManager(db_path)
    rooms = rm.list_all()
    rm.close()
    if not rooms:
        return 0

    store = MessageStore(db_path)
    # 기존 row 정리(멱등 보장: 부분 적재 후 재실행 케이스 대비)
    store._conn.execute("DELETE FROM messages")
    store._conn.commit()

    appended = 0
    conn = await aiosqlite.connect(db_path)
    try:
        saver = AsyncSqliteSaver(conn)
        await saver.setup()
        for room in rooms:
            try:
                cps = saver.alist({"configurable": {"thread_id": room.id}})
                latest = None
                async for cp in cps:
                    latest = cp
                    break
                if latest is None:
                    continue
                state_msgs = latest.checkpoint.get("channel_values", {}).get("messages", [])
                for m in state_msgs:
                    role = _role_of(m)
                    if not role:
                        continue
                    rid = store.append(
                        room_id=room.id,
                        role=role,
                        content=getattr(m, "content", "") or "",
                        created_at=datetime.now(timezone.utc).isoformat(),
                    )
                    if rid is not None:
                        appended += 1
            except Exception as e:
                print(f"[backfill] room={room.id} failed: {e}", file=sys.stderr)
    finally:
        await conn.close()
        store.close()
    return appended


def _main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.backfill_messages <db_path>")
        sys.exit(1)
    n = asyncio.run(backfill(sys.argv[1]))
    print(f"backfill complete: {n} messages appended")


if __name__ == "__main__":
    _main()
