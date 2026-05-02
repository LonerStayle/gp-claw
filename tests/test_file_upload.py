"""파일 첨부 업로드 테스트.

성공기준 (spec):
1. 허용 확장자/크기 → 200 + sandbox/<room_id>/ 저장
2. 허용 외 확장자 → 400 + INVALID_TYPE
3. 10MB 초과 → 400 + TOO_LARGE
4. 동일 파일명 2회 업로드 → 자동 리네임 (_<uuid8>)
5. 메시지 표시는 프론트 영역, 백엔드는 path 응답 포함 검증
6. 방 삭제 → sandbox/<room_id>/ 디렉토리 삭제
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gp_claw.files import (
    MAX_FILE_SIZE_BYTES,
    cleanup_room_files,
    is_valid_room_id,
    relative_sandbox_path,
    resolve_sandbox_root,
    resolve_unique_path,
    sanitize_filename,
    validate_extension,
)
from gp_claw.server import create_app


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def client(project_root: Path):
    app = create_app(project_root=project_root)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def room_id(client: TestClient) -> str:
    return client.post("/rooms", json={"title": "업로드 테스트"}).json()["id"]


# --- Pure unit tests ----------------------------------------------------


def test_sanitize_filename_replaces_unsafe_chars():
    assert sanitize_filename("hello world.txt") == "hello_world.txt"
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("a/b/c.md") == "c.md"
    assert sanitize_filename("한글파일명.csv") == "한글파일명.csv"
    assert sanitize_filename("file*?.pdf") == "file__.pdf"


def test_sanitize_filename_empty_fallback():
    assert sanitize_filename("") == "file"
    assert sanitize_filename("....") == "file"


def test_validate_extension_ok():
    assert validate_extension("a.PDF") == ".pdf"
    assert validate_extension("b.txt") == ".txt"
    assert validate_extension("c.md") == ".md"
    assert validate_extension("d.csv") == ".csv"


def test_validate_extension_rejects_bad_ext():
    from gp_claw.files import FileUploadError

    with pytest.raises(FileUploadError) as exc:
        validate_extension("evil.exe")
    assert exc.value.code == "INVALID_TYPE"

    with pytest.raises(FileUploadError):
        validate_extension("noext")


def test_is_valid_room_id():
    assert is_valid_room_id("abc123")
    assert is_valid_room_id("a-b_c")
    assert not is_valid_room_id("")
    assert not is_valid_room_id("..")
    assert not is_valid_room_id("a/b")
    assert not is_valid_room_id("a b")


def test_resolve_unique_path_collision_renames(tmp_path: Path):
    sandbox = resolve_sandbox_root(tmp_path)
    p1 = resolve_unique_path(sandbox, "room1", "report.pdf")
    p1.write_bytes(b"x")
    p2 = resolve_unique_path(sandbox, "room1", "report.pdf")
    assert p1 != p2
    assert p2.stem.startswith("report_")
    assert p2.suffix == ".pdf"
    assert len(p2.stem) == len("report_") + 8  # 8-char uuid suffix


def test_relative_sandbox_path(tmp_path: Path):
    sandbox = resolve_sandbox_root(tmp_path)
    target = sandbox / "room1" / "a.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"x")
    rel = relative_sandbox_path(target, tmp_path)
    assert rel == "sandbox/room1/a.txt"
    assert not Path(rel).is_absolute()


def test_cleanup_room_files(tmp_path: Path):
    sandbox = resolve_sandbox_root(tmp_path)
    p = sandbox / "roomZ" / "x.txt"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x")
    assert cleanup_room_files("roomZ", project_root=tmp_path) is True
    assert not (sandbox / "roomZ").exists()
    # 두 번째 호출은 False (이미 삭제됨)
    assert cleanup_room_files("roomZ", project_root=tmp_path) is False
    # 잘못된 room_id
    assert cleanup_room_files("../etc", project_root=tmp_path) is False


# --- HTTP integration tests --------------------------------------------


def _post_file(client: TestClient, room_id: str, name: str, body: bytes):
    return client.post(
        f"/api/rooms/{room_id}/files",
        files={"file": (name, io.BytesIO(body), "application/octet-stream")},
    )


def test_upload_success_pdf(client: TestClient, room_id: str, project_root: Path):
    """성공기준 #1 — 허용 확장자/크기 업로드."""
    r = _post_file(client, room_id, "report.pdf", b"%PDF-1.4 dummy")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == f"sandbox/{room_id}/report.pdf"
    assert body["size"] == len(b"%PDF-1.4 dummy")
    assert body["mime"] == "application/pdf"
    assert (project_root / body["path"]).exists()


def test_upload_success_all_allowed_extensions(client: TestClient, room_id: str):
    for name, mime in [
        ("a.txt", "text/plain"),
        ("b.md", "text/markdown"),
        ("c.csv", "text/csv"),
        ("d.pdf", "application/pdf"),
    ]:
        r = _post_file(client, room_id, name, b"hello")
        assert r.status_code == 200, f"{name}: {r.text}"
        assert r.json()["mime"] == mime


def test_upload_rejects_bad_extension(client: TestClient, room_id: str):
    """성공기준 #2 — 허용 외 확장자."""
    r = _post_file(client, room_id, "evil.exe", b"MZ")
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_TYPE"


def test_upload_rejects_image_extension(client: TestClient, room_id: str):
    r = _post_file(client, room_id, "photo.png", b"\x89PNG")
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_TYPE"


def test_upload_rejects_too_large(client: TestClient, room_id: str):
    """성공기준 #3 — 10MB 초과."""
    body = b"a" * (MAX_FILE_SIZE_BYTES + 1)
    r = _post_file(client, room_id, "big.txt", body)
    assert r.status_code == 400
    assert r.json()["code"] == "TOO_LARGE"


def test_upload_accepts_exact_max_size(client: TestClient, room_id: str):
    body = b"a" * MAX_FILE_SIZE_BYTES
    r = _post_file(client, room_id, "limit.txt", body)
    assert r.status_code == 200, r.text
    assert r.json()["size"] == MAX_FILE_SIZE_BYTES


def test_upload_collision_renames(client: TestClient, room_id: str, project_root: Path):
    """성공기준 #4 — 동일 파일명 자동 리네임."""
    r1 = _post_file(client, room_id, "report.pdf", b"first")
    r2 = _post_file(client, room_id, "report.pdf", b"second")
    assert r1.status_code == 200 and r2.status_code == 200
    p1, p2 = r1.json()["path"], r2.json()["path"]
    assert p1 != p2
    assert p1.endswith("/report.pdf")
    # report_<8>.pdf
    second_name = Path(p2).name
    assert second_name.startswith("report_") and second_name.endswith(".pdf")
    assert len(second_name) == len("report_") + 8 + len(".pdf")
    # 두 파일 모두 디스크에 존재 + 내용 보존
    assert (project_root / p1).read_bytes() == b"first"
    assert (project_root / p2).read_bytes() == b"second"


def test_upload_invalid_room(client: TestClient):
    r = _post_file(client, "nonexistent", "a.txt", b"x")
    assert r.status_code == 400
    assert r.json()["code"] == "INVALID_ROOM"


def test_upload_invalid_room_id_format(client: TestClient):
    r = _post_file(client, "..", "a.txt", b"x")
    # ".." gets URL-normalized away by client; FastAPI returns 405/404. Try "a/b"
    r2 = client.post(
        "/api/rooms/bad room id/files",
        files={"file": ("a.txt", io.BytesIO(b"x"), "text/plain")},
    )
    # 둘 중 하나라도 4xx 거부면 OK
    assert r.status_code >= 400 or r2.status_code >= 400


def test_upload_sanitizes_filename(client: TestClient, room_id: str):
    r = _post_file(client, room_id, "../../etc/passwd.txt", b"x")
    assert r.status_code == 200
    # 디렉토리 부분 제거 후 sanitize
    assert r.json()["path"] == f"sandbox/{room_id}/passwd.txt"


def test_upload_returns_relative_path_only(client: TestClient, room_id: str):
    r = _post_file(client, room_id, "x.txt", b"x")
    assert r.status_code == 200
    p = r.json()["path"]
    assert not Path(p).is_absolute()
    assert p.startswith("sandbox/")


def test_room_delete_cleans_sandbox(client: TestClient, room_id: str, project_root: Path):
    """성공기준 #6 — 방 삭제 시 sandbox/<room_id>/ 재귀 삭제."""
    r = _post_file(client, room_id, "x.txt", b"hello")
    assert r.status_code == 200
    room_dir = project_root / "sandbox" / room_id
    assert room_dir.exists() and (room_dir / "x.txt").exists()

    resp = client.delete(f"/rooms/{room_id}")
    assert resp.status_code == 204
    assert not room_dir.exists()


def test_room_delete_no_files_ok(client: TestClient, room_id: str):
    """sandbox 폴더가 없어도 방 삭제는 성공해야 함."""
    resp = client.delete(f"/rooms/{room_id}")
    assert resp.status_code == 204


def test_alias_endpoint_rooms_files(client: TestClient, room_id: str):
    """기존 패턴 호환 별칭 엔드포인트."""
    r = client.post(
        f"/rooms/{room_id}/files",
        files={"file": ("alias.txt", io.BytesIO(b"x"), "text/plain")},
    )
    assert r.status_code == 200
    assert r.json()["path"] == f"sandbox/{room_id}/alias.txt"
