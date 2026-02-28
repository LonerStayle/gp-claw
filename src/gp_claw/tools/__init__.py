from gp_claw.tools.registry import ToolRegistry, ToolSafety
from gp_claw.tools.safe_file import create_safe_file_tools
from gp_claw.tools.dangerous_file import create_dangerous_file_tools


def create_tool_registry(workspace_root: str) -> ToolRegistry:
    """도구 레지스트리 생성. Safe + Dangerous 파일 도구 포함."""
    return ToolRegistry(
        safe_tools=create_safe_file_tools(workspace_root),
        dangerous_tools=create_dangerous_file_tools(workspace_root),
    )


__all__ = [
    "ToolRegistry",
    "ToolSafety",
    "create_safe_file_tools",
    "create_dangerous_file_tools",
    "create_tool_registry",
]
