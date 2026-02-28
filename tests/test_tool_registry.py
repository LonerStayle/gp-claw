from unittest.mock import MagicMock

from gp_claw.tools.registry import ToolRegistry, ToolSafety


def _make_tool(name: str) -> MagicMock:
    t = MagicMock()
    t.name = name
    return t


def test_tool_safety_enum_values():
    assert ToolSafety.SAFE == "safe"
    assert ToolSafety.DANGEROUS == "dangerous"


def test_registry_all_tools():
    safe = [_make_tool("file_read")]
    dangerous = [_make_tool("file_write")]
    reg = ToolRegistry(safe_tools=safe, dangerous_tools=dangerous)
    assert len(reg.all_tools) == 2


def test_registry_classify_safe():
    reg = ToolRegistry(safe_tools=[_make_tool("file_read")])
    assert reg.classify("file_read") == ToolSafety.SAFE


def test_registry_classify_dangerous():
    reg = ToolRegistry(dangerous_tools=[_make_tool("file_write")])
    assert reg.classify("file_write") == ToolSafety.DANGEROUS


def test_registry_classify_unknown_raises():
    import pytest
    reg = ToolRegistry()
    with pytest.raises(ValueError, match="Unknown tool"):
        reg.classify("nonexistent")
