from enum import Enum


class ToolSafety(str, Enum):
    SAFE = "safe"
    DANGEROUS = "dangerous"


class ToolRegistry:
    """도구를 Safe/Dangerous로 분류하고 관리하는 레지스트리."""

    def __init__(self, safe_tools: list | None = None, dangerous_tools: list | None = None):
        self.safe_tools = safe_tools or []
        self.dangerous_tools = dangerous_tools or []

    @property
    def all_tools(self) -> list:
        return self.safe_tools + self.dangerous_tools

    @property
    def safe_names(self) -> set[str]:
        return {t.name for t in self.safe_tools}

    @property
    def dangerous_names(self) -> set[str]:
        return {t.name for t in self.dangerous_tools}

    def classify(self, tool_name: str) -> ToolSafety:
        if tool_name in self.safe_names:
            return ToolSafety.SAFE
        if tool_name in self.dangerous_names:
            return ToolSafety.DANGEROUS
        raise ValueError(f"Unknown tool: {tool_name}")
