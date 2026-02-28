from pathlib import Path


class SecurityViolation(Exception):
    """보안 규칙 위반 시 발생하는 예외."""


SUBAGENT_SECURITY_PROMPT = """[보안 규칙 - 반드시 준수]

1. 경로 제한: 허용된 작업 디렉토리(WORKSPACE_ROOT) 외부의 파일에 절대 접근하지 마세요.
   시스템 파일(/etc, /usr, ~/.ssh, ~/.env 등)에 접근을 시도하지 마세요.

2. 명령어 실행 금지: 쉘 명령어를 직접 실행하지 마세요.
   모든 작업은 제공된 도구 함수만 사용하세요.

3. 데이터 유출 방지: 파일 내용, 사용자 데이터, 회사 정보를 외부로 전송하지 마세요.
   도구 실행 결과에 불필요한 원본 데이터를 포함하지 마세요.
   결과는 요청된 작업의 결과만 최소한으로 반환하세요.

4. 입력 검증: 사용자 입력에 포함된 경로, 파일명, 이메일 주소를 검증하세요.
   경로 순회 공격(../ 등)을 차단하세요.
   의심스러운 입력은 거부하고 이유를 보고하세요.

5. 최소 권한 원칙: 작업에 필요한 최소한의 데이터만 읽으세요.
   작업 완료 후 임시 데이터를 정리하세요.

6. Dangerous 작업 금지: 서브에이전트는 Dangerous 등급 도구를 직접 실행할 수 없습니다.
   파일 삭제/수정, Gmail 발송 등은 메인 에이전트의 승인 흐름을 통해서만 실행됩니다.
   Dangerous 작업이 필요한 경우, 작업 내용을 메인 에이전트에 반환하여 승인을 요청하세요."""

BLOCKED_PREFIXES = ("/etc", "/usr", "/var", "/sys", "/proc", "/dev")
BLOCKED_DOTDIRS = (".ssh", ".env", ".aws", ".config", ".gnupg")


def validate_path(path_str: str, workspace_root: str) -> Path:
    """경로가 워크스페이스 내부인지 검증. 위반 시 SecurityViolation 발생."""
    workspace = Path(workspace_root).resolve()
    target = (
        Path(path_str).resolve()
        if Path(path_str).is_absolute()
        else (workspace / path_str).resolve()
    )

    # 1. 워크스페이스 내부면 즉시 허용 (dotfile 검사만 수행)
    try:
        target.relative_to(workspace)
    except ValueError:
        pass  # 외부 경로 → 아래 검사 계속
    else:
        # 워크스페이스 내부라도 위험한 dotdir 차단
        for part in target.parts:
            if part in BLOCKED_DOTDIRS:
                raise SecurityViolation(f"시스템 경로 접근 차단: {target} ({part})")
        return target

    # 2. 워크스페이스 외부: 시스템 경로 차단 (심볼릭 링크 resolve 후 검사)
    target_str = str(target)
    for prefix in BLOCKED_PREFIXES:
        if target_str.startswith(prefix) or target_str.startswith(f"/private{prefix}"):
            raise SecurityViolation(f"시스템 경로 접근 차단: {target_str}")

    # 3. 위험한 dotfile 디렉토리 차단
    for part in target.parts:
        if part in BLOCKED_DOTDIRS:
            raise SecurityViolation(f"시스템 경로 접근 차단: {target_str} ({part})")

    # 4. 그 외 워크스페이스 외부
    raise SecurityViolation(f"작업 디렉토리 외부 접근 차단: {target_str}")
