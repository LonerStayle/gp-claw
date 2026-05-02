"""WS user_message 처리 시 첨부 본문이 LLM 입력에 prepend되는지 검증.

성공기준 #1, #2, #3 — LLM이 받는 messages를 캡처해서 본문이 들어 있는지 확인.

LLM mocking: 기존 test_ws_agent.py 와 동일 패턴 (MagicMock + AsyncMock(side_effect=...))
- agent simple_agent 의 .ainvoke 는 정상 응답을 반환해야 LangGraph가 종료된다.
- 업로드 단계의 요약 호출과 WS 단계의 에이전트 호출 모두 같은 mock을 통과한다.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from gp_claw.server import create_app


def _make_capturing_llm(response_content: str = "MOCK_RESPONSE"):
    """모든 ainvoke 호출을 calls에 캡처하는 MagicMock 기반 LLM."""
    mock_llm = MagicMock()
    calls: list[list[Any]] = []

    async def _ainvoke(messages):
        calls.append(list(messages))
        return AIMessage(content=response_content)

    mock_llm.ainvoke = AsyncMock(side_effect=_ainvoke)
    mock_llm._calls = calls
    return mock_llm


def _make_failing_then_ok_llm(ok_response: str = "OK"):
    """첫 호출은 실패, 이후 호출은 ok_response 반환."""
    mock_llm = MagicMock()
    calls: list[list[Any]] = []
    counter = {"n": 0}

    async def _ainvoke(messages):
        counter["n"] += 1
        calls.append(list(messages))
        if counter["n"] == 1:
            raise RuntimeError("강제 요약 실패")
        return AIMessage(content=ok_response)

    mock_llm.ainvoke = AsyncMock(side_effect=_ainvoke)
    mock_llm._calls = calls
    return mock_llm


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


def _post_file(client: TestClient, room_id: str, name: str, body: bytes):
    return client.post(
        f"/api/rooms/{room_id}/files",
        files={"file": (name, io.BytesIO(body), "application/octet-stream")},
    )


def _flatten_calls(calls: list[list[Any]]) -> str:
    out = []
    for call in calls:
        for m in call:
            if hasattr(m, "content") and isinstance(m.content, str):
                out.append(m.content)
    return "\n".join(out)


def _drain_until_done(ws, max_iter: int = 30) -> list[dict]:
    msgs = []
    for _ in range(max_iter):
        m = ws.receive_json()
        msgs.append(m)
        if m["type"] in ("assistant_done", "error"):
            return msgs
    return msgs


def test_ws_user_message_prepends_small_attachment_raw(project_root: Path):
    """성공기준 #1: 작은 첨부(.md) → LLM input에 원문 그대로 prepend."""
    mock = _make_capturing_llm("응답")
    app = create_app(llm=mock, project_root=project_root)
    with TestClient(app) as client:
        room_id = client.post("/rooms", json={"title": "t"}).json()["id"]
        body = "사용자 노트 본문 abc".encode("utf-8")
        r = _post_file(client, room_id, "n.md", body)
        assert r.status_code == 200
        # raw 모드 — 업로드 단계에서는 LLM 호출 없음
        upload_call_count = len(mock._calls)

        with client.websocket_connect(f"/ws/{room_id}") as ws:
            ws.send_json(
                {
                    "type": "user_message",
                    "content": "이 노트 요약해줘",
                    "attachments": [
                        {
                            "path": f"sandbox/{room_id}/n.md",
                            "filename": "n.md",
                            "size": len(body),
                            "mime": "text/markdown",
                        }
                    ],
                }
            )
            _drain_until_done(ws)

    ws_calls = mock._calls[upload_call_count:]
    assert ws_calls, "Agent did not call LLM"
    flat = _flatten_calls(ws_calls)
    assert "[첨부 파일 본문]" in flat
    assert "사용자 노트 본문 abc" in flat
    assert "이 노트 요약해줘" in flat


def test_ws_user_message_prepends_large_attachment_summary(project_root: Path):
    """성공기준 #2: 큰 첨부 → 업로드 시 요약 → WS에 요약 결과 prepend."""
    mock = _make_capturing_llm("MOCK_SUMMARY_LARGE_DOC")
    app = create_app(llm=mock, project_root=project_root)
    with TestClient(app) as client:
        room_id = client.post("/rooms", json={"title": "t2"}).json()["id"]
        body = ("이것은 큰 문서입니다. " * 1000).encode("utf-8")
        r = _post_file(client, room_id, "big.txt", body)
        assert r.status_code == 200
        assert r.json()["extraction_mode"] == "summary"

        upload_call_count = len(mock._calls)

        with client.websocket_connect(f"/ws/{room_id}") as ws:
            ws.send_json(
                {
                    "type": "user_message",
                    "content": "이 문서 분석해줘",
                    "attachments": [
                        {
                            "path": f"sandbox/{room_id}/big.txt",
                            "filename": "big.txt",
                            "size": len(body),
                            "mime": "text/plain",
                        }
                    ],
                }
            )
            _drain_until_done(ws)

    ws_calls = mock._calls[upload_call_count:]
    flat = _flatten_calls(ws_calls)
    assert "MOCK_SUMMARY_LARGE_DOC" in flat
    assert "이 문서 분석해줘" in flat
    # 원문이 5번 이상 반복되는 패턴은 없음 — 요약본만
    assert ("이것은 큰 문서입니다. " * 5) not in flat


def test_ws_user_message_degraded_label(project_root: Path):
    """성공기준 #3: 요약 실패 → '일부만 반영' 라벨이 LLM input에 들어감."""
    mock = _make_failing_then_ok_llm("OK")
    app = create_app(llm=mock, project_root=project_root)
    with TestClient(app) as client:
        room_id = client.post("/rooms", json={"title": "t3"}).json()["id"]
        body = ("abcdefg " * 2000).encode("utf-8")
        r = _post_file(client, room_id, "fb.txt", body)
        assert r.status_code == 200
        body_json = r.json()
        assert body_json["extraction_mode"] == "truncated"
        assert body_json["degraded"] is True

        upload_call_count = len(mock._calls)

        with client.websocket_connect(f"/ws/{room_id}") as ws:
            ws.send_json(
                {
                    "type": "user_message",
                    "content": "분석해줘",
                    "attachments": [
                        {
                            "path": f"sandbox/{room_id}/fb.txt",
                            "filename": "fb.txt",
                            "size": len(body),
                            "mime": "text/plain",
                        }
                    ],
                }
            )
            _drain_until_done(ws)

    ws_calls = mock._calls[upload_call_count:]
    flat = _flatten_calls(ws_calls)
    assert "일부만 반영" in flat
    assert "분석해줘" in flat


def test_ws_user_message_no_attachments_unchanged(project_root: Path):
    """첨부 없으면 user_text만 LLM에 전달."""
    mock = _make_capturing_llm("응답")
    app = create_app(llm=mock, project_root=project_root)
    with TestClient(app) as client:
        with client.websocket_connect("/ws/session-noatt") as ws:
            ws.send_json({"type": "user_message", "content": "안녕"})
            _drain_until_done(ws)
    flat = _flatten_calls(mock._calls)
    assert "[첨부 파일 본문]" not in flat
    assert "안녕" in flat
