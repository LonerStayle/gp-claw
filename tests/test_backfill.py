import asyncio

import pytest

from gp_claw.messages import MessageStore
from gp_claw.rooms import RoomManager
from scripts.backfill_messages import backfill


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "bf.db")


def test_backfill_empty_db_is_zero(db):
    # rooms 테이블 미존재 → 안전 처리
    count = asyncio.run(backfill(db))
    assert count == 0


def test_backfill_is_idempotent(db):
    rm = RoomManager(db)
    rm.create(room_id="r1", title="t")
    rm.close()
    store = MessageStore(db)
    store.append("r1", "user", "manual1")
    store.append("r1", "assistant", "manual2")
    store.close()
    asyncio.run(backfill(db))
    asyncio.run(backfill(db))
    s2 = MessageStore(db)
    msgs = s2.list_by_room("r1")
    s2.close()
    # 백필은 체크포인트 소스만 사용하므로 manually inject한 row는 사라지고
    # 빈 체크포인트일 경우 0개. 같은 결과를 두 번 보장.
    assert len(msgs) == 0
