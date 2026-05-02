"""업로드 엔드포인트 ↔ 추출 통합 테스트.

성공기준 매핑:
- #1: small text 첨부 → 응답에 extraction='ready' & mode='raw'
- #2: large text → mode='summary' (LLM mocked)
- #3: 요약 실패 mock → degraded=True, mode='truncated'
- #5: 한글 파일명 업로드 → chip/응답에 한글 그대로
- #7: 메타 파일이 sandbox 외부로 새지 않음 (트래버설 방어)
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from gp_claw.server import create_app


class _StubLLMOK:
    async def ainvoke(self, messages: list[Any]) -> Any:
        class _R:
            content = "통합 테스트용 모킹 요약 결과 — 핵심 정보가 들어 있습니다."

        return _R()


class _StubLLMFail:
    async def ainvoke(self, messages: list[Any]) -> Any:
        raise RuntimeError("강제 실패")


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def client_ok(project_root: Path):
    app = create_app(llm=_StubLLMOK(), project_root=project_root)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_fail(project_root: Path):
    app = create_app(llm=_StubLLMFail(), project_root=project_root)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_no_llm(project_root: Path):
    app = create_app(project_root=project_root)
    with TestClient(app) as c:
        yield c


def _create_room(client: TestClient) -> str:
    return client.post("/rooms", json={"title": "추출 테스트"}).json()["id"]


def _post_file(client: TestClient, room_id: str, name: str, body: bytes):
    return client.post(
        f"/api/rooms/{room_id}/files",
        files={"file": (name, io.BytesIO(body), "application/octet-stream")},
    )


# ---- 성공기준 #1 -----------------------------------------------------------


def test_upload_small_text_raw_mode(client_ok: TestClient, project_root: Path):
    """작은 .md → extraction=ready, mode=raw, 원문 캐시."""
    room_id = _create_room(client_ok)
    body = "핵심 노트 100자 내외".encode("utf-8")
    r = _post_file(client_ok, room_id, "note.md", body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["extraction"] == "ready"
    assert j["extraction_mode"] == "raw"
    assert j["degraded"] is False
    # 메타 파일 확인
    meta_file = project_root / "sandbox" / room_id / ".meta" / "note.md.json"
    assert meta_file.exists()
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    assert meta["mode"] == "raw"
    assert "핵심 노트" in meta["content_for_llm"]


# ---- 성공기준 #2 -----------------------------------------------------------


def test_upload_large_text_summary_mode(client_ok: TestClient, project_root: Path):
    """8K 초과 → mode=summary (raw 아님)."""
    room_id = _create_room(client_ok)
    body = ("이것은 큰 문서입니다. " * 1000).encode("utf-8")
    r = _post_file(client_ok, room_id, "big.txt", body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["extraction"] == "ready"
    assert j["extraction_mode"] == "summary"
    assert j["degraded"] is False
    assert j["summary_chars"] > 0
    # 메타에는 요약본만 — 원문 일부 문자열이 그대로 들어가지는 않음
    meta_file = project_root / "sandbox" / room_id / ".meta" / "big.txt.json"
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    assert meta["mode"] == "summary"
    assert "통합 테스트용 모킹 요약" in meta["content_for_llm"]


# ---- 성공기준 #3 -----------------------------------------------------------


def test_upload_summary_failure_falls_back(client_fail: TestClient, project_root: Path):
    """요약 LLM 강제 실패 → mode=truncated, degraded=True."""
    room_id = _create_room(client_fail)
    body = ("abcdefg " * 2000).encode("utf-8")
    r = _post_file(client_fail, room_id, "fallback.txt", body)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["extraction"] == "ready"  # 업로드는 success — 폴백 적용
    assert j["extraction_mode"] == "truncated"
    assert j["degraded"] is True
    assert j["extraction_error"]


def test_upload_no_llm_large_falls_back(client_no_llm: TestClient, project_root: Path):
    """LLM이 없는 경우(에코 모드)도 큰 문서면 truncated 폴백."""
    room_id = _create_room(client_no_llm)
    body = ("xxx" * 5000).encode("utf-8")
    r = _post_file(client_no_llm, room_id, "no_llm.txt", body)
    assert r.status_code == 200
    j = r.json()
    assert j["extraction_mode"] == "truncated"
    assert j["degraded"] is True


# ---- 성공기준 #5 -----------------------------------------------------------


def test_upload_korean_filename_preserved(client_ok: TestClient, project_root: Path):
    """한글 파일명 업로드 → 응답·디스크에 한글 그대로 보존."""
    room_id = _create_room(client_ok)
    r = _post_file(client_ok, room_id, "보고서_한글_3차.pdf", b"%PDF-1.4 dummy")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "보고서_한글_3차.pdf" in j["path"]
    assert j["filename"] == "보고서_한글_3차.pdf"
    # 디스크에도 한글로 저장
    saved = project_root / j["path"]
    assert saved.exists()
    assert "보고서_한글_3차" in saved.name


def test_upload_korean_md_then_extraction_ok(client_ok: TestClient, project_root: Path):
    """한글 파일명 .md → 메타 파일도 한글 이름 + .json."""
    room_id = _create_room(client_ok)
    body = "한글 본문".encode("utf-8")
    r = _post_file(client_ok, room_id, "회의록.md", body)
    assert r.status_code == 200
    meta_file = project_root / "sandbox" / room_id / ".meta" / "회의록.md.json"
    assert meta_file.exists()


# ---- 폴링 엔드포인트 -------------------------------------------------------


def test_extraction_polling_endpoint(client_ok: TestClient, project_root: Path):
    room_id = _create_room(client_ok)
    body = "짧은 텍스트".encode("utf-8")
    r = _post_file(client_ok, room_id, "poll.md", body)
    assert r.status_code == 200
    # 폴링
    r2 = client_ok.get(f"/api/rooms/{room_id}/files/poll.md/extraction")
    assert r2.status_code == 200
    meta = r2.json()
    assert meta["mode"] == "raw"
    assert "짧은 텍스트" in meta["content_for_llm"]


def test_extraction_polling_missing(client_ok: TestClient):
    room_id = _create_room(client_ok)
    r = client_ok.get(f"/api/rooms/{room_id}/files/nope.md/extraction")
    assert r.status_code == 404


def test_extraction_polling_invalid_room(client_ok: TestClient):
    r = client_ok.get("/api/rooms/..%2Fetc/files/x.md/extraction")
    # FastAPI normalizes; either 400/404 acceptable as both reject access
    assert r.status_code >= 400


# ---- 메타 트래버설 방어 ---------------------------------------------------


def test_meta_dir_inside_sandbox(client_ok: TestClient, project_root: Path):
    """메타 파일은 항상 sandbox 디렉토리 내부에 생성됨."""
    room_id = _create_room(client_ok)
    _post_file(client_ok, room_id, "trav.md", b"abc")
    meta_file = project_root / "sandbox" / room_id / ".meta" / "trav.md.json"
    assert meta_file.exists()
    # resolve 결과가 sandbox 하위인지
    sandbox_root = (project_root / "sandbox").resolve()
    assert meta_file.resolve().is_relative_to(sandbox_root)


def test_room_delete_cleans_meta(client_ok: TestClient, project_root: Path):
    """방 삭제 시 .meta까지 함께 정리됨 (cleanup_room_files가 디렉토리 트리 삭제)."""
    room_id = _create_room(client_ok)
    _post_file(client_ok, room_id, "to_del.md", b"hi")
    meta_dir = project_root / "sandbox" / room_id / ".meta"
    assert meta_dir.exists()
    resp = client_ok.delete(f"/rooms/{room_id}")
    assert resp.status_code == 204
    assert not meta_dir.exists()
    assert not (project_root / "sandbox" / room_id).exists()
