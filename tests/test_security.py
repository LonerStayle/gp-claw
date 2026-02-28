import pytest

from gp_claw.security import SUBAGENT_SECURITY_PROMPT, validate_path, SecurityViolation


def test_security_prompt_contains_key_rules():
    assert "경로 제한" in SUBAGENT_SECURITY_PROMPT
    assert "명령어 실행 금지" in SUBAGENT_SECURITY_PROMPT
    assert "데이터 유출 방지" in SUBAGENT_SECURITY_PROMPT
    assert "입력 검증" in SUBAGENT_SECURITY_PROMPT
    assert "최소 권한" in SUBAGENT_SECURITY_PROMPT
    assert "Dangerous 작업 금지" in SUBAGENT_SECURITY_PROMPT


def test_validate_path_allows_workspace_paths(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "test.txt"
    target.touch()
    result = validate_path(str(target), str(workspace))
    assert result == target


def test_validate_path_blocks_traversal(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(SecurityViolation):
        validate_path("../../../etc/passwd", str(workspace))


def test_validate_path_blocks_system_paths(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(SecurityViolation, match="시스템 경로"):
        validate_path("/etc/passwd", str(workspace))


def test_validate_path_blocks_dotfiles(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(SecurityViolation, match="시스템 경로"):
        validate_path(str(workspace / ".ssh" / "id_rsa"), str(workspace))
