"""첨부 파일 본문 추출 + LLM 컨텍스트 주입을 위한 모듈.

스펙: 2026-05-02-pdf-content-injection-spec.md

주요 기능:
- PDF/텍스트 본문 추출 (pypdf, UTF-8/cp949 폴백)
- 임계치 분기: 8,000자 미만 → raw, 초과 → LLM 요약
- 요약 실패 시 truncation 폴백 (degraded=True)
- 메타 캐시: sandbox/<room_id>/.meta/<filename>.json
- 트래버설 방어 (Path.resolve + relative_to)

자유 영역 선택:
- 임계치: 8,000자
- 동기 처리 (FastAPI 응답 안에서 await — 사용자가 chip 상태로 진행 확인)
- 요약 프롬프트: 한국어, 1,500~2,000자 목표
- 입력 토큰 보호 한도: 80,000자
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from pypdf import PdfReader

logger = logging.getLogger(__name__)

# ---- 임계치 / 한도 상수 (워커 자율) ----
SUMMARY_THRESHOLD_CHARS: int = 8_000
SUMMARY_INPUT_LIMIT_CHARS: int = 80_000
TRUNCATION_LIMIT_CHARS: int = 7_000
SUMMARY_TARGET_CHARS_LO: int = 1_500
SUMMARY_TARGET_CHARS_HI: int = 2_000

# 메타 디렉토리명
META_DIRNAME: str = ".meta"


class ExtractionError(RuntimeError):
    """본문 추출 단계 실패 (LLM 호출 전)."""


def _read_pdf_text(path: Path) -> str:
    """pypdf로 PDF 페이지 순서대로 텍스트 추출."""
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception as e:  # noqa: BLE001
            logger.warning("PDF page extract failed: %s", e)
            parts.append("")
    return "\n".join(parts).strip()


def _read_text_file(path: Path) -> str:
    """UTF-8 우선, cp949 폴백으로 텍스트 파일 읽기."""
    raw = path.read_bytes()
    for encoding in ("utf-8", "cp949", "euc-kr", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    # 마지막 폴백 — 깨진 문자 무시
    return raw.decode("utf-8", errors="replace")


def extract_text(path: Path) -> str:
    """확장자에 따라 텍스트 추출.

    지원: .pdf .txt .md .csv
    """
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _read_pdf_text(path)
    if ext in {".txt", ".md", ".csv"}:
        return _read_text_file(path)
    raise ExtractionError(f"Unsupported extension: {ext}")


def build_summary_prompt(text: str) -> str:
    """LLM 요약 프롬프트 — 한국어, 핵심 요약 1,500~2,000자 목표."""
    return (
        "당신은 한국어 문서 요약 전문가입니다. 아래 첨부 문서의 핵심 내용을 한국어로 요약해주세요.\n\n"
        "요약 지침:\n"
        f"- 분량: 약 {SUMMARY_TARGET_CHARS_LO:,}~{SUMMARY_TARGET_CHARS_HI:,}자\n"
        "- 문서의 주제, 주요 논점, 결정사항, 숫자/날짜/고유명사 등 사실 정보를 빠뜨리지 마세요.\n"
        "- 불필요한 수사나 인사말은 빼고 정보 위주로 작성합니다.\n"
        "- 표나 목록이 있다면 핵심만 추려 자연어로 풀어 설명합니다.\n"
        "- 문서 외부 추측은 하지 마세요. 원문에 없는 내용은 만들지 않습니다.\n\n"
        "[원문 시작]\n"
        f"{text}\n"
        "[원문 끝]\n\n"
        "위 지침에 맞춰 한국어 요약을 작성하세요."
    )


async def summarize_with_llm(llm: Any, text: str, *, timeout: float = 30.0) -> str:
    """LLM으로 요약 호출.

    Args:
        llm: langchain BaseChatModel (.ainvoke 가능). 테스트에서는 mock 주입.
        text: 원문 (이미 SUMMARY_INPUT_LIMIT_CHARS 안으로 잘려야 함)
        timeout: 타임아웃 (초)

    Returns:
        요약 텍스트 (비어있으면 ExtractionError).
    """
    import asyncio

    if llm is None:
        raise ExtractionError("LLM not available")

    # 입력 토큰 보호 — 너무 큰 텍스트는 자르고 요약
    if len(text) > SUMMARY_INPUT_LIMIT_CHARS:
        text = text[:SUMMARY_INPUT_LIMIT_CHARS] + "\n... [이하 생략]"

    from langchain_core.messages import HumanMessage

    prompt = build_summary_prompt(text)
    msg = HumanMessage(content=prompt)

    try:
        result = await asyncio.wait_for(llm.ainvoke([msg]), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise ExtractionError("Summary timeout") from e
    except Exception as e:  # noqa: BLE001
        raise ExtractionError(f"Summary LLM error: {e}") from e

    summary = (result.content if hasattr(result, "content") else str(result)).strip()
    if not summary:
        raise ExtractionError("Empty summary from LLM")
    return summary


def truncate_with_marker(text: str, *, limit: int = TRUNCATION_LIMIT_CHARS) -> str:
    """앞 N자 자르고 ‘...[이하 생략, 원본 X자]’ 마커 부착."""
    if len(text) <= limit:
        return text
    head = text[:limit].rstrip()
    return f"{head}\n... [이하 생략, 원본 {len(text):,}자]"


# ---- 메타 캐시 (sandbox/<room>/.meta/<file>.json) ----------------------


def _meta_dir_for_room(sandbox_root: Path, room_id: str) -> Path:
    """방 메타 디렉토리 경로. sandbox_root 내부인지 검증 후 반환."""
    sandbox_root = sandbox_root.resolve()
    meta_dir = (sandbox_root / room_id / META_DIRNAME).resolve()
    # 트래버설 방어
    try:
        meta_dir.relative_to(sandbox_root)
    except ValueError as e:
        raise ExtractionError("Invalid meta path (traversal)") from e
    return meta_dir


def meta_path_for(sandbox_root: Path, room_id: str, filename: str) -> Path:
    """첨부의 메타 JSON 경로. sandbox_root 내부 검증."""
    meta_dir = _meta_dir_for_room(sandbox_root, room_id)
    # filename은 이미 sanitize된 값이어야 함
    candidate = (meta_dir / f"{filename}.json").resolve()
    try:
        candidate.relative_to(sandbox_root)
    except ValueError as e:
        raise ExtractionError("Invalid meta path (traversal)") from e
    return candidate


def write_meta(meta_file: Path, data: dict[str, Any]) -> None:
    meta_file.parent.mkdir(parents=True, exist_ok=True)
    meta_file.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_meta(meta_file: Path) -> Optional[dict[str, Any]]:
    if not meta_file.exists():
        return None
    try:
        return json.loads(meta_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---- 핵심 진입점 -----------------------------------------------------------


async def process_attachment(
    *,
    file_path: Path,
    sandbox_root: Path,
    room_id: str,
    filename: str,
    llm: Any | None,
    threshold: int = SUMMARY_THRESHOLD_CHARS,
    summary_timeout: float = 30.0,
) -> dict[str, Any]:
    """첨부 파일에서 본문 추출 + 임계치 분기 + 메타 캐시 작성.

    Returns:
        메타 dict (캐시 파일에 저장된 내용과 동일).
    """
    meta: dict[str, Any] = {
        "filename": filename,
        "extracted_at": now_iso(),
        "extracted_chars": 0,
        "mode": "raw",
        "content_for_llm": "",
        "summary_chars": 0,
        "degraded": False,
        "error": None,
    }

    # 1) 추출
    try:
        text = extract_text(file_path)
    except Exception as e:  # noqa: BLE001
        logger.warning("Extraction failed for %s: %s", file_path, e)
        meta["mode"] = "error"
        meta["error"] = str(e)
        meta["degraded"] = True
        meta_file = meta_path_for(sandbox_root, room_id, filename)
        write_meta(meta_file, meta)
        return meta

    meta["extracted_chars"] = len(text)

    # 2) 임계치 분기
    if len(text) <= threshold:
        meta["mode"] = "raw"
        meta["content_for_llm"] = text
        meta_file = meta_path_for(sandbox_root, room_id, filename)
        write_meta(meta_file, meta)
        return meta

    # 3) LLM 요약 시도
    try:
        summary = await summarize_with_llm(llm, text, timeout=summary_timeout)
        meta["mode"] = "summary"
        meta["content_for_llm"] = summary
        meta["summary_chars"] = len(summary)
    except ExtractionError as e:
        # 폴백 — truncation
        logger.warning("Summary failed, falling back to truncation: %s", e)
        meta["mode"] = "truncated"
        meta["content_for_llm"] = truncate_with_marker(text)
        meta["degraded"] = True
        meta["error"] = str(e)

    meta_file = meta_path_for(sandbox_root, room_id, filename)
    write_meta(meta_file, meta)
    return meta


def load_attachment_meta(
    *, sandbox_root: Path, room_id: str, filename: str
) -> Optional[dict[str, Any]]:
    """기존 메타 캐시 로드. 없으면 None."""
    try:
        meta_file = meta_path_for(sandbox_root, room_id, filename)
    except ExtractionError:
        return None
    return read_meta(meta_file)


# ---- WS user_message prepend 빌더 ------------------------------------------


def build_attachment_context(
    *,
    sandbox_root: Path,
    attachments: list[dict[str, Any]],
    user_text: str,
) -> str:
    """첨부 본문을 user_text 앞에 prepend한 최종 HumanMessage content 생성.

    Args:
        sandbox_root: sandbox 디렉토리 절대 경로
        attachments: [{"path": "sandbox/<room>/foo.pdf", "filename": "foo.pdf", ...}, ...]
        user_text: 원문 사용자 메시지

    Returns:
        delimiter로 묶인 prepend된 content 문자열.
        attachments가 비어 있으면 user_text 그대로.
    """
    if not attachments:
        return user_text

    lines: list[str] = ["[첨부 파일 본문]", ""]
    has_any_content = False

    for att in attachments:
        rel_path = att.get("path", "")
        filename = att.get("filename") or Path(rel_path).name
        # path 포맷: sandbox/<room_id>/<filename>
        path_parts = Path(rel_path).parts
        room_id = ""
        if len(path_parts) >= 2 and path_parts[0] in ("sandbox", "sandbox/"):
            room_id = path_parts[1]

        meta = None
        if room_id:
            meta = load_attachment_meta(
                sandbox_root=sandbox_root, room_id=room_id, filename=filename
            )

        if not meta:
            lines.append(
                f"- {rel_path} (본문 미반영: 캐시 없음 또는 추출 미완료)"
            )
            lines.append("")
            continue

        mode = meta.get("mode", "raw")
        content = meta.get("content_for_llm", "")
        if not content:
            reason = meta.get("error") or "본문 비어있음"
            lines.append(f"- {rel_path} (본문 미반영: {reason})")
            lines.append("")
            continue

        mode_label = {
            "raw": "원문",
            "summary": "요약",
            "truncated": "일부만 반영 — 잘린 원문",
            "error": "본문 미반영",
        }.get(mode, mode)
        lines.append(f"- {rel_path} ({mode_label}):")
        lines.append(content)
        lines.append("")
        has_any_content = True

    if not has_any_content:
        # 모두 미반영이라면 안내만 부착하고 user_text와 결합
        lines.append("─────")
        lines.append("")
        lines.append(user_text)
        return "\n".join(lines)

    lines.append("─────")
    lines.append("")
    lines.append(user_text)
    return "\n".join(lines)
