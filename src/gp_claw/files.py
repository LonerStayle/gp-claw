"""파일 첨부(업로드) — sandbox 디렉토리 관리.

스펙: spec.md (file-attachment-spec)
- 허용 확장자: .pdf .txt .md .csv
- 최대 크기: 10 MB
- 저장 위치: <project_root>/sandbox/<room_id>/<filename>
- 충돌 시: <basename>_<uuid8>.<ext> 로 자동 리네임
- 파일명 sanitize: 영숫자/한글/._- 외 문자는 '_'로 치환
- 응답 경로: 항상 프로젝트 루트 기준 상대 경로
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from uuid import uuid4

ALLOWED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".txt", ".md", ".csv"})
MAX_FILE_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB
DEFAULT_SANDBOX_DIRNAME: str = "sandbox"

# 영숫자, 한글(가-힣), 점/언더스코어/하이픈 외의 문자는 모두 '_'로 치환
_SANITIZE_RE = re.compile(r"[^A-Za-z0-9가-힣._\-]")
# room_id 형식 검증: 영숫자/언더스코어/하이픈 1~128자 (UUID hex 포함)
_ROOM_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,128}$")


class FileUploadError(ValueError):
    """파일 업로드 검증 실패."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def is_valid_room_id(room_id: str) -> bool:
    """room_id 형식 유효성 — 경로 트래버설/주입 방어용."""
    if not room_id or not isinstance(room_id, str):
        return False
    if room_id in (".", ".."):
        return False
    return bool(_ROOM_ID_RE.match(room_id))


def sanitize_filename(filename: str) -> str:
    """파일명 정화. 디렉토리 구분자 제거 + 허용 외 문자 치환.

    빈 문자열이 되거나 점만 남으면 fallback 'file' 사용.
    """
    if not filename:
        return "file"
    # 디렉토리 구성 요소 제거 — 경로 트래버설 방어
    base = Path(filename).name
    # 허용 외 문자 → '_'
    cleaned = _SANITIZE_RE.sub("_", base)
    # 선두/말미 점·공백 제거
    cleaned = cleaned.strip(". ")
    if not cleaned:
        return "file"
    return cleaned


def validate_extension(filename: str) -> str:
    """확장자 검증. 정상 시 소문자 확장자(.txt 등) 반환, 아니면 FileUploadError."""
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileUploadError(
            "INVALID_TYPE",
            f"허용되지 않은 확장자입니다: {ext or '(없음)'}",
        )
    return ext


def validate_size(size: int) -> None:
    """크기 검증. 초과 시 FileUploadError(TOO_LARGE)."""
    if size > MAX_FILE_SIZE_BYTES:
        raise FileUploadError(
            "TOO_LARGE",
            f"파일 크기가 한도(10MB)를 초과했습니다: {size} bytes",
        )


def resolve_sandbox_root(project_root: Path | str | None = None) -> Path:
    """sandbox 디렉토리 경로 (자동 생성)."""
    root = Path(project_root) if project_root else Path.cwd()
    sandbox = (root / DEFAULT_SANDBOX_DIRNAME).resolve()
    sandbox.mkdir(parents=True, exist_ok=True)
    return sandbox


def resolve_unique_path(sandbox_root: Path, room_id: str, filename: str) -> Path:
    """저장할 최종 경로 결정. 충돌 시 '<base>_<uuid8>.<ext>' 형식으로 리네임."""
    room_dir = (sandbox_root / room_id).resolve()
    # 트래버설 방어 — sandbox_root 하위인지 검증
    try:
        room_dir.relative_to(sandbox_root)
    except ValueError as e:
        raise FileUploadError("INVALID_ROOM", "잘못된 room_id 경로") from e

    room_dir.mkdir(parents=True, exist_ok=True)

    target = room_dir / filename
    target_resolved = target.resolve()
    try:
        target_resolved.relative_to(sandbox_root)
    except ValueError as e:
        raise FileUploadError("INVALID_TYPE", "잘못된 파일 경로") from e

    if not target_resolved.exists():
        return target_resolved

    # 충돌 — uuid8 suffix
    base = target.stem
    ext = target.suffix
    while True:
        suffix = uuid4().hex[:8]
        candidate = (room_dir / f"{base}_{suffix}{ext}").resolve()
        try:
            candidate.relative_to(sandbox_root)
        except ValueError as e:
            raise FileUploadError("INVALID_TYPE", "잘못된 파일 경로") from e
        if not candidate.exists():
            return candidate


def relative_sandbox_path(absolute_path: Path, project_root: Path | str | None = None) -> str:
    """sandbox 절대경로를 프로젝트 루트 기준 상대 경로 문자열(POSIX)로 반환."""
    root = Path(project_root) if project_root else Path.cwd()
    rel = absolute_path.resolve().relative_to(root.resolve())
    # 일관된 표시(POSIX 슬래시)
    return rel.as_posix()


def cleanup_room_files(room_id: str, project_root: Path | str | None = None) -> bool:
    """방 삭제 시 sandbox/<room_id>/ 디렉토리 재귀 삭제.

    Returns:
        실제로 삭제된 디렉토리가 있었으면 True.
    """
    if not is_valid_room_id(room_id):
        return False
    sandbox_root = resolve_sandbox_root(project_root)
    room_dir = (sandbox_root / room_id).resolve()
    try:
        room_dir.relative_to(sandbox_root)
    except ValueError:
        return False
    if not room_dir.exists() or not room_dir.is_dir():
        return False
    shutil.rmtree(room_dir, ignore_errors=True)
    return True


def guess_mime(filename: str) -> str:
    """간단 MIME 추정 (.pdf .txt .md .csv 한정)."""
    ext = Path(filename).suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".md": "text/markdown",
        ".csv": "text/csv",
    }.get(ext, "application/octet-stream")
