"""첨부 파일 본문 추출 + LLM 주입 테스트.

성공기준 매핑:
- #1: 작은 텍스트 → raw 모드, 원문 그대로
- #2: 큰 PDF → 요약 모드 (raw 아님)
- #3: 요약 LLM 실패 → truncation + degraded=True
- #5: 한글 파일명 보존
- #7: pdf 추출 / 임계치 분기 / 요약 폴백 / 메타 트래버설 방어 / 한글 sanitize
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from pypdf import PdfWriter
from pypdf.generic import RectangleObject

from gp_claw.extraction import (
    SUMMARY_THRESHOLD_CHARS,
    ExtractionError,
    build_attachment_context,
    extract_text,
    load_attachment_meta,
    meta_path_for,
    process_attachment,
    truncate_with_marker,
)
from gp_claw.files import resolve_sandbox_root, sanitize_filename


# ---- Helpers ---------------------------------------------------------------


def _make_pdf_with_text(path: Path, text: str) -> None:
    """간단한 PDF 생성기 — reportlab으로 텍스트 기반 PDF.

    pypdf가 추출 가능하도록 reportlab으로 텍스트 페이지 작성.
    """
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path))
    # 한 줄에 80자, 한 페이지에 ~50줄
    width, height = 595, 842  # A4 portrait
    line_height = 14
    max_lines_per_page = 50
    line_chars = 80

    lines: list[str] = []
    cur = 0
    while cur < len(text):
        chunk = text[cur : cur + line_chars]
        lines.append(chunk)
        cur += line_chars

    page_lines: list[list[str]] = []
    for i in range(0, len(lines), max_lines_per_page):
        page_lines.append(lines[i : i + max_lines_per_page])

    if not page_lines:
        page_lines = [[""]]

    for page in page_lines:
        y = height - 40
        for line in page:
            c.drawString(40, y, line)
            y -= line_height
        c.showPage()
    c.save()


def _make_empty_pdf(path: Path) -> None:
    """텍스트 없는 빈 PDF (pypdf 기본)."""
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    with path.open("wb") as f:
        writer.write(f)


# ---- Pure unit tests -------------------------------------------------------


def test_extract_text_txt(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("hello 한글", encoding="utf-8")
    assert extract_text(p) == "hello 한글"


def test_extract_text_md(tmp_path: Path):
    p = tmp_path / "b.md"
    p.write_text("# 제목\n본문", encoding="utf-8")
    assert "제목" in extract_text(p)


def test_extract_text_csv(tmp_path: Path):
    p = tmp_path / "c.csv"
    p.write_text("a,b\n1,2", encoding="utf-8")
    assert extract_text(p).startswith("a,b")


def test_extract_text_cp949_fallback(tmp_path: Path):
    p = tmp_path / "d.txt"
    p.write_bytes("안녕하세요".encode("cp949"))
    out = extract_text(p)
    assert "안녕하세요" in out


def test_extract_text_pdf(tmp_path: Path):
    p = tmp_path / "doc.pdf"
    _make_pdf_with_text(p, "Hello World 한글본문 테스트")
    out = extract_text(p)
    # pypdf의 한글 추출 품질은 폰트에 의존하지만 영문은 확실히 추출됨
    assert "Hello" in out or "World" in out


def test_extract_text_unsupported_extension(tmp_path: Path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"binary")
    with pytest.raises(ExtractionError):
        extract_text(p)


def test_truncate_with_marker_short():
    assert truncate_with_marker("short", limit=10) == "short"


def test_truncate_with_marker_long():
    text = "a" * 10_000
    out = truncate_with_marker(text, limit=100)
    assert len(out) < 200
    assert "이하 생략" in out
    assert "10,000" in out  # 원본 길이 명시


# ---- 메타 캐시 + 트래버설 방어 ---------------------------------------------


def test_meta_path_for_traversal_defense(tmp_path: Path):
    sandbox = resolve_sandbox_root(tmp_path)
    # 정상
    p = meta_path_for(sandbox, "room1", "report.pdf")
    assert str(p).startswith(str(sandbox))
    assert p.name == "report.pdf.json"
    # 트래버설 시도 — room_id에 ../
    with pytest.raises(ExtractionError):
        meta_path_for(sandbox, "../etc", "x.txt")


def test_meta_path_for_filename_traversal(tmp_path: Path):
    sandbox = resolve_sandbox_root(tmp_path)
    # filename에 .. 포함 시 sanitize 거친 후라야 안전 — 직접 호출 시 방어
    with pytest.raises(ExtractionError):
        meta_path_for(sandbox, "room1", "../../../etc/passwd")


def test_load_attachment_meta_missing(tmp_path: Path):
    sandbox = resolve_sandbox_root(tmp_path)
    assert (
        load_attachment_meta(
            sandbox_root=sandbox, room_id="room1", filename="missing.pdf"
        )
        is None
    )


# ---- process_attachment — 임계치 분기 + LLM 모킹 ---------------------------


class _MockLLMOK:
    """요약 성공 모킹."""

    async def ainvoke(self, messages: list[Any]) -> Any:
        class _Result:
            content = "이것은 모킹된 요약입니다. " + ("핵심 " * 200)

        return _Result()


class _MockLLMFail:
    """요약 실패 모킹."""

    async def ainvoke(self, messages: list[Any]) -> Any:
        raise RuntimeError("LLM 강제 실패")


class _MockLLMEmpty:
    """빈 응답 모킹."""

    async def ainvoke(self, messages: list[Any]) -> Any:
        class _Result:
            content = "   "

        return _Result()


@pytest.mark.asyncio
async def test_process_attachment_small_text_raw(tmp_path: Path):
    """성공기준 #1: 8K 미만 텍스트 → raw 모드, 원문 그대로."""
    sandbox = resolve_sandbox_root(tmp_path)
    room_dir = sandbox / "room1"
    room_dir.mkdir(parents=True, exist_ok=True)
    file_path = room_dir / "small.md"
    file_path.write_text("# 짧은 노트\n핵심 내용 100자 정도", encoding="utf-8")

    meta = await process_attachment(
        file_path=file_path,
        sandbox_root=sandbox,
        room_id="room1",
        filename="small.md",
        llm=_MockLLMOK(),
    )
    assert meta["mode"] == "raw"
    assert meta["content_for_llm"].startswith("# 짧은 노트")
    assert meta["degraded"] is False
    assert meta["error"] is None
    # 메타 파일이 디스크에 기록됨
    meta_file = meta_path_for(sandbox, "room1", "small.md")
    assert meta_file.exists()
    on_disk = json.loads(meta_file.read_text(encoding="utf-8"))
    assert on_disk["mode"] == "raw"


@pytest.mark.asyncio
async def test_process_attachment_large_summary(tmp_path: Path):
    """성공기준 #2: 8K 초과 → 요약 모드 (raw 아님)."""
    sandbox = resolve_sandbox_root(tmp_path)
    room_dir = sandbox / "roomB"
    room_dir.mkdir(parents=True, exist_ok=True)
    file_path = room_dir / "big.txt"
    huge = ("이것은 큰 문서입니다. " * 1000)  # 약 1.4만 자
    assert len(huge) > SUMMARY_THRESHOLD_CHARS
    file_path.write_text(huge, encoding="utf-8")

    meta = await process_attachment(
        file_path=file_path,
        sandbox_root=sandbox,
        room_id="roomB",
        filename="big.txt",
        llm=_MockLLMOK(),
    )
    assert meta["mode"] == "summary"
    assert "모킹된 요약" in meta["content_for_llm"]
    assert meta["summary_chars"] > 0
    assert meta["degraded"] is False
    # 요약이므로 raw가 아님 — 원문 prefix가 그대로 들어가지 않음
    assert "이것은 큰 문서입니다." not in meta["content_for_llm"]


@pytest.mark.asyncio
async def test_process_attachment_summary_failure_falls_back(tmp_path: Path):
    """성공기준 #3: 요약 LLM 실패 → truncation 폴백 + degraded=True."""
    sandbox = resolve_sandbox_root(tmp_path)
    room_dir = sandbox / "roomC"
    room_dir.mkdir(parents=True, exist_ok=True)
    file_path = room_dir / "fail.txt"
    huge = "abcdefg " * 2000  # ~16K
    file_path.write_text(huge, encoding="utf-8")

    meta = await process_attachment(
        file_path=file_path,
        sandbox_root=sandbox,
        room_id="roomC",
        filename="fail.txt",
        llm=_MockLLMFail(),
    )
    assert meta["mode"] == "truncated"
    assert meta["degraded"] is True
    assert meta["error"] is not None
    assert "이하 생략" in meta["content_for_llm"]
    # truncation 길이가 원본보다 짧아야 함
    assert len(meta["content_for_llm"]) < len(huge)


@pytest.mark.asyncio
async def test_process_attachment_summary_empty_falls_back(tmp_path: Path):
    """빈 응답도 실패로 처리 → truncation 폴백."""
    sandbox = resolve_sandbox_root(tmp_path)
    room_dir = sandbox / "roomE"
    room_dir.mkdir(parents=True, exist_ok=True)
    file_path = room_dir / "empty_resp.txt"
    huge = "x" * 10_000
    file_path.write_text(huge, encoding="utf-8")

    meta = await process_attachment(
        file_path=file_path,
        sandbox_root=sandbox,
        room_id="roomE",
        filename="empty_resp.txt",
        llm=_MockLLMEmpty(),
    )
    assert meta["mode"] == "truncated"
    assert meta["degraded"] is True


@pytest.mark.asyncio
async def test_process_attachment_no_llm_large_falls_back(tmp_path: Path):
    """LLM이 None일 때 큰 문서 → truncation 폴백."""
    sandbox = resolve_sandbox_root(tmp_path)
    room_dir = sandbox / "roomD"
    room_dir.mkdir(parents=True, exist_ok=True)
    file_path = room_dir / "big.txt"
    huge = "z" * 12_000
    file_path.write_text(huge, encoding="utf-8")

    meta = await process_attachment(
        file_path=file_path,
        sandbox_root=sandbox,
        room_id="roomD",
        filename="big.txt",
        llm=None,
    )
    assert meta["mode"] == "truncated"
    assert meta["degraded"] is True


@pytest.mark.asyncio
async def test_process_attachment_pdf(tmp_path: Path):
    """PDF 추출 → 임계치 분기 정상 동작."""
    sandbox = resolve_sandbox_root(tmp_path)
    room_dir = sandbox / "roomP"
    room_dir.mkdir(parents=True, exist_ok=True)
    file_path = room_dir / "doc.pdf"
    _make_pdf_with_text(file_path, "Test report content. " * 20)

    meta = await process_attachment(
        file_path=file_path,
        sandbox_root=sandbox,
        room_id="roomP",
        filename="doc.pdf",
        llm=_MockLLMOK(),
    )
    assert meta["mode"] in ("raw", "summary")
    assert meta["extracted_chars"] > 0


@pytest.mark.asyncio
async def test_process_attachment_unsupported_records_error(tmp_path: Path):
    """지원하지 않는 확장자 — 에러 메타 기록."""
    sandbox = resolve_sandbox_root(tmp_path)
    room_dir = sandbox / "roomX"
    room_dir.mkdir(parents=True, exist_ok=True)
    file_path = room_dir / "unknown.bin"
    file_path.write_bytes(b"binary")

    meta = await process_attachment(
        file_path=file_path,
        sandbox_root=sandbox,
        room_id="roomX",
        filename="unknown.bin",
        llm=_MockLLMOK(),
    )
    assert meta["mode"] == "error"
    assert meta["degraded"] is True
    assert meta["error"]


# ---- build_attachment_context — HumanMessage prepend -----------------------


@pytest.mark.asyncio
async def test_build_attachment_context_with_meta(tmp_path: Path):
    sandbox = resolve_sandbox_root(tmp_path)
    room_dir = sandbox / "roomMSG"
    room_dir.mkdir(parents=True, exist_ok=True)
    file_path = room_dir / "note.md"
    file_path.write_text("핵심 노트 내용입니다.", encoding="utf-8")
    await process_attachment(
        file_path=file_path,
        sandbox_root=sandbox,
        room_id="roomMSG",
        filename="note.md",
        llm=_MockLLMOK(),
    )

    out = build_attachment_context(
        sandbox_root=sandbox,
        attachments=[
            {
                "path": "sandbox/roomMSG/note.md",
                "filename": "note.md",
                "size": 0,
                "mime": "text/markdown",
            }
        ],
        user_text="이 파일 요약해줘",
    )
    assert "[첨부 파일 본문]" in out
    assert "sandbox/roomMSG/note.md" in out
    assert "(원문)" in out
    assert "핵심 노트 내용입니다" in out
    assert "이 파일 요약해줘" in out
    # delimiter 위치 — user_text는 마지막 라인
    assert out.strip().endswith("이 파일 요약해줘")


def test_build_attachment_context_missing_meta(tmp_path: Path):
    sandbox = resolve_sandbox_root(tmp_path)
    out = build_attachment_context(
        sandbox_root=sandbox,
        attachments=[
            {
                "path": "sandbox/roomNONE/missing.pdf",
                "filename": "missing.pdf",
                "size": 0,
                "mime": "application/pdf",
            }
        ],
        user_text="질문",
    )
    assert "본문 미반영" in out
    assert "질문" in out


def test_build_attachment_context_no_attachments():
    out = build_attachment_context(
        sandbox_root=Path("/tmp/anything"),
        attachments=[],
        user_text="그냥 질문",
    )
    assert out == "그냥 질문"


@pytest.mark.asyncio
async def test_build_attachment_context_degraded_label(tmp_path: Path):
    """truncated mode → '일부만 반영' 라벨."""
    sandbox = resolve_sandbox_root(tmp_path)
    room_dir = sandbox / "roomT"
    room_dir.mkdir(parents=True, exist_ok=True)
    file_path = room_dir / "long.txt"
    huge = "y" * 12_000
    file_path.write_text(huge, encoding="utf-8")

    await process_attachment(
        file_path=file_path,
        sandbox_root=sandbox,
        room_id="roomT",
        filename="long.txt",
        llm=_MockLLMFail(),
    )
    out = build_attachment_context(
        sandbox_root=sandbox,
        attachments=[
            {
                "path": "sandbox/roomT/long.txt",
                "filename": "long.txt",
                "size": 12_000,
                "mime": "text/plain",
            }
        ],
        user_text="질문입니다",
    )
    assert "일부만 반영" in out


# ---- 한글 sanitize 회귀 ---------------------------------------------------


def test_korean_filename_preserved():
    """성공기준 #5 회귀: 한글 파일명 보존."""
    out = sanitize_filename("보고서_한글_3차.pdf")
    assert out == "보고서_한글_3차.pdf"


def test_korean_filename_with_spaces_preserved_chars():
    out = sanitize_filename("보 고 서.pdf")
    # 공백은 _로 치환되지만 한글은 살아남아야 함
    assert "보" in out and "고" in out and "서" in out
    assert out.endswith(".pdf")


def test_korean_filename_complex():
    out = sanitize_filename("회의록(2026년)_최종.md")
    # 괄호는 _로, 한글은 보존
    assert "회의록" in out and "최종" in out
    assert out.endswith(".md")


def test_meta_filename_with_korean(tmp_path: Path):
    """한글 파일명도 메타 경로 생성/조회가 정상 동작."""
    sandbox = resolve_sandbox_root(tmp_path)
    safe = sanitize_filename("보고서_한글_3차.pdf")
    p = meta_path_for(sandbox, "roomK", safe)
    assert "보고서_한글_3차.pdf.json" == p.name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{}", encoding="utf-8")
    meta = load_attachment_meta(
        sandbox_root=sandbox, room_id="roomK", filename=safe
    )
    assert meta == {}
