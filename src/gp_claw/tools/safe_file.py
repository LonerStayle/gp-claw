from datetime import datetime
from pathlib import Path

from langchain_core.tools import tool

from gp_claw.security import validate_path


def create_safe_file_tools(workspace_root: str) -> list:
    """Safe 파일 도구 생성. workspace_root를 클로저로 바인딩."""

    @tool
    def file_read(path: str, encoding: str = "utf-8") -> dict:
        """지정된 경로의 파일 내용을 텍스트로 반환합니다.

        Args:
            path: 워크스페이스 내 파일 경로
            encoding: 파일 인코딩 (기본: utf-8)
        """
        validated = validate_path(path, workspace_root)
        content = validated.read_text(encoding=encoding)
        return {
            "content": content,
            "size_bytes": validated.stat().st_size,
            "path": str(validated),
        }

    @tool
    def file_search(pattern: str, directory: str = ".") -> dict:
        """파일명/확장자/패턴으로 워크스페이스 내 파일을 검색합니다.

        Args:
            pattern: glob 패턴 (예: *.xlsx, **/*.txt)
            directory: 검색 시작 디렉토리 (기본: 워크스페이스 루트)
        """
        base = validate_path(directory, workspace_root)
        matches = []
        for p in sorted(base.glob(pattern)):
            if p.is_file():
                stat = p.stat()
                matches.append({
                    "path": str(p),
                    "name": p.name,
                    "size_bytes": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
        return {"files": matches}

    @tool
    def file_list(directory: str = ".") -> dict:
        """지정 디렉토리의 파일/폴더 목록을 반환합니다.

        Args:
            directory: 대상 디렉토리 (기본: 워크스페이스 루트)
        """
        base = validate_path(directory, workspace_root)
        entries = []
        for p in sorted(base.iterdir()):
            entries.append({
                "name": p.name,
                "type": "dir" if p.is_dir() else "file",
                "size_bytes": p.stat().st_size if p.is_file() else 0,
            })
        return {"entries": entries}

    return [file_read, file_search, file_list]
