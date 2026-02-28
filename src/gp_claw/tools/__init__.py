from gp_claw.tools.registry import ToolRegistry, ToolSafety
from gp_claw.tools.safe_file import create_safe_file_tools


def create_tool_registry(workspace_root: str) -> ToolRegistry:
    """도구 레지스트리 생성. Safe 도구만 포함 (Phase 2C에서 Dangerous 추가)."""
    return ToolRegistry(
        safe_tools=create_safe_file_tools(workspace_root),
    )


__all__ = ["ToolRegistry", "ToolSafety", "create_safe_file_tools", "create_tool_registry"]
