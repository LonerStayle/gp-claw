from pathlib import Path

from langchain_core.tools import tool

from gp_claw.security import validate_path


def create_dangerous_file_tools(workspace_root: str) -> list:
    """Dangerous 파일 도구 생성. 실행 전 사용자 승인 필수."""

    @tool
    def file_write(path: str, content: str, encoding: str = "utf-8") -> dict:
        """새 파일을 생성하거나 기존 파일을 덮어씁니다. (승인 필요)

        Args:
            path: 워크스페이스 내 파일 경로
            content: 쓸 내용
            encoding: 파일 인코딩 (기본: utf-8)
        """
        validated = validate_path(path, workspace_root)
        action = "overwritten" if validated.exists() else "created"
        validated.parent.mkdir(parents=True, exist_ok=True)
        validated.write_text(content, encoding=encoding)
        return {
            "path": str(validated),
            "size_bytes": validated.stat().st_size,
            "action": action,
        }

    @tool
    def file_delete(path: str) -> dict:
        """지정된 파일을 삭제합니다. (승인 필요)

        Args:
            path: 삭제할 파일 경로
        """
        validated = validate_path(path, workspace_root)
        if not validated.exists():
            raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
        size = validated.stat().st_size
        validated.unlink()
        return {"deleted": str(validated), "size_bytes": size}

    @tool
    def file_move(source: str, destination: str) -> dict:
        """파일을 이동하거나 이름을 변경합니다. (승인 필요)

        Args:
            source: 원본 파일 경로
            destination: 대상 파일 경로
        """
        src = validate_path(source, workspace_root)
        dst = validate_path(destination, workspace_root)
        if not src.exists():
            raise FileNotFoundError(f"원본 파일을 찾을 수 없습니다: {source}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.rename(dst)
        return {"source": str(src), "destination": str(dst)}

    return [file_write, file_delete, file_move]
