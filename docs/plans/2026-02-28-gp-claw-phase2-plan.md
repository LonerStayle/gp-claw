# Phase 2: Tool System + Human-in-the-Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Safe/Dangerous 파일 도구 시스템과 Human-in-the-Loop 승인 워크플로우를 구현하여, 에이전트가 안전한 도구는 바로 실행하고 위험한 도구는 사용자 승인 후 실행하도록 한다.

**Architecture:** Tool Registry 패턴으로 도구를 Safe/Dangerous로 분류. LangGraph 그래프에 tool routing 노드 추가 (safe → ToolNode 직접 실행, dangerous → `interrupt()`로 승인 요청 후 실행). WebSocket 프로토콜 확장으로 승인 카드 지원.

**Tech Stack:** LangGraph (ToolNode, interrupt, Command), langchain-core (`@tool` decorator), FastAPI WebSocket, pathlib

---

## 참고 문서

| 문서 | 경로 |
|------|------|
| 전체 설계 | `docs/plans/2026-02-28-gp-claw-design.md` |
| Phase 1 플랜 (완료) | `docs/plans/2026-02-28-gp-claw-phase1-plan.md` |
| 핸드오프 | `HANDOFF.md` |

## Phase 2 범위

- **2A**: Tool Registry + Safe 파일 도구 (`file_read`, `file_search`, `file_list`)
- **2B**: Agent-Tool 연결 (LangGraph tool routing, WebSocket tool 결과)
- **2C**: Dangerous 파일 도구 (`file_write`, `file_delete`, `file_move`) + HITL 승인 워크플로우

## 파일 맵

| 작업 | 파일 |
|------|------|
| Create | `src/gp_claw/tools/__init__.py` |
| Create | `src/gp_claw/tools/registry.py` |
| Create | `src/gp_claw/tools/safe_file.py` |
| Create | `src/gp_claw/tools/dangerous_file.py` |
| Modify | `src/gp_claw/agent.py` |
| Modify | `src/gp_claw/server.py` |
| Modify | `src/gp_claw/__main__.py` |
| Create | `tests/test_tool_registry.py` |
| Create | `tests/test_safe_file_tools.py` |
| Create | `tests/test_dangerous_file_tools.py` |
| Create | `tests/test_agent_tools.py` |
| Create | `tests/test_ws_approval.py` |
| Modify | `tests/conftest.py` |

---

## Phase 2A: Tool Infrastructure + Safe File Tools

### Task 1: Tool Registry + ToolSafety

**Files:**
- Create: `src/gp_claw/tools/__init__.py`
- Create: `src/gp_claw/tools/registry.py`
- Test: `tests/test_tool_registry.py`

**Step 1: Write the failing test**

```python
# tests/test_tool_registry.py
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
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_tool_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gp_claw.tools'`

**Step 3: Write minimal implementation**

```python
# src/gp_claw/tools/__init__.py
```

```python
# src/gp_claw/tools/registry.py
from dataclasses import dataclass, field
from enum import Enum


class ToolSafety(str, Enum):
    SAFE = "safe"
    DANGEROUS = "dangerous"


@dataclass
class ToolRegistry:
    safe_tools: list = field(default_factory=list)
    dangerous_tools: list = field(default_factory=list)

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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_tool_registry.py -v`
Expected: ALL PASS (5 tests)

**Step 5: Commit**

```bash
git add src/gp_claw/tools/__init__.py src/gp_claw/tools/registry.py tests/test_tool_registry.py
git commit -m "feat: add ToolRegistry and ToolSafety enum"
```

---

### Task 2: Safe File Tools (file_read, file_search, file_list)

**Files:**
- Create: `src/gp_claw/tools/safe_file.py`
- Modify: `src/gp_claw/tools/__init__.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_safe_file_tools.py`

**Step 1: Add workspace fixture to conftest**

```python
# tests/conftest.py — 기존 내용 유지하고 아래 추가
@pytest.fixture
def workspace(tmp_path):
    ws = tmp_path / "workspace"
    ws.mkdir()
    return ws
```

**Step 2: Write the failing tests**

```python
# tests/test_safe_file_tools.py
import pytest

from gp_claw.tools.safe_file import create_safe_file_tools
from gp_claw.security import SecurityViolation


@pytest.fixture
def tools(workspace):
    return create_safe_file_tools(str(workspace))


@pytest.fixture
def file_read(tools):
    return tools[0]


@pytest.fixture
def file_search(tools):
    return tools[1]


@pytest.fixture
def file_list(tools):
    return tools[2]


# --- file_read ---

def test_file_read_returns_content(workspace, file_read):
    (workspace / "hello.txt").write_text("안녕하세요")
    result = file_read.invoke({"path": "hello.txt"})
    assert result["content"] == "안녕하세요"
    assert result["size_bytes"] > 0
    assert "hello.txt" in result["path"]


def test_file_read_blocks_outside_workspace(workspace, file_read):
    with pytest.raises(Exception):
        file_read.invoke({"path": "/etc/passwd"})


# --- file_search ---

def test_file_search_finds_matching_files(workspace, file_search):
    (workspace / "data.xlsx").touch()
    (workspace / "report.xlsx").touch()
    (workspace / "notes.txt").touch()
    result = file_search.invoke({"pattern": "*.xlsx"})
    names = {f["name"] for f in result["files"]}
    assert names == {"data.xlsx", "report.xlsx"}


def test_file_search_respects_directory(workspace, file_search):
    sub = workspace / "sub"
    sub.mkdir()
    (sub / "a.txt").touch()
    (workspace / "b.txt").touch()
    result = file_search.invoke({"pattern": "*.txt", "directory": "sub"})
    assert len(result["files"]) == 1
    assert result["files"][0]["name"] == "a.txt"


# --- file_list ---

def test_file_list_returns_entries(workspace, file_list):
    (workspace / "file.txt").write_text("hello")
    (workspace / "subdir").mkdir()
    result = file_list.invoke({"directory": "."})
    names = {e["name"] for e in result["entries"]}
    assert "file.txt" in names
    assert "subdir" in names


def test_file_list_shows_types(workspace, file_list):
    (workspace / "f.txt").touch()
    (workspace / "d").mkdir()
    result = file_list.invoke({"directory": "."})
    entries = {e["name"]: e["type"] for e in result["entries"]}
    assert entries["f.txt"] == "file"
    assert entries["d"] == "dir"
```

**Step 3: Run test to verify it fails**

Run: `pytest tests/test_safe_file_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'gp_claw.tools.safe_file'`

**Step 4: Write minimal implementation**

```python
# src/gp_claw/tools/safe_file.py
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
```

Update `__init__.py`:

```python
# src/gp_claw/tools/__init__.py
from gp_claw.tools.registry import ToolRegistry, ToolSafety
from gp_claw.tools.safe_file import create_safe_file_tools

__all__ = ["ToolRegistry", "ToolSafety", "create_safe_file_tools"]
```

**Step 5: Run test to verify it passes**

Run: `pytest tests/test_safe_file_tools.py -v`
Expected: ALL PASS (6 tests)

**Step 6: Run all tests**

Run: `pytest -v`
Expected: ALL PASS (기존 16 + 신규 11 = 27 tests)

**Step 7: Commit — Phase 2A 완료**

```bash
git add src/gp_claw/tools/ tests/test_tool_registry.py tests/test_safe_file_tools.py tests/conftest.py
git commit -m "feat(Phase 2A): tool registry + safe file tools (file_read, file_search, file_list)"
```

---

## Phase 2B: Agent-Tool Integration

### Task 3: Agent Graph with Tool Routing

**Files:**
- Modify: `src/gp_claw/agent.py`
- Test: `tests/test_agent_tools.py`

**Step 1: Write the failing tests**

```python
# tests/test_agent_tools.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver

from gp_claw.agent import create_agent, AgentState
from gp_claw.tools.registry import ToolRegistry, ToolSafety
from gp_claw.tools.safe_file import create_safe_file_tools


@pytest.fixture
def safe_registry(workspace):
    return ToolRegistry(safe_tools=create_safe_file_tools(str(workspace)))


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.bind_tools = MagicMock(return_value=llm)
    return llm


def test_agent_with_registry_has_tool_nodes(mock_llm, safe_registry):
    graph = create_agent(mock_llm, registry=safe_registry)
    nodes = set(graph.get_graph().nodes.keys())
    assert "agent" in nodes
    assert "safe_tools" in nodes


def test_agent_without_registry_has_simple_graph(mock_llm):
    """Phase 1 호환: registry=None이면 기존 단순 그래프."""
    graph = create_agent(mock_llm, registry=None)
    nodes = set(graph.get_graph().nodes.keys())
    assert "agent" in nodes
    assert "safe_tools" not in nodes


@pytest.mark.asyncio
async def test_agent_routes_safe_tool_call(workspace, mock_llm, safe_registry):
    (workspace / "test.txt").write_text("hello world")

    mock_llm.ainvoke = AsyncMock(side_effect=[
        # 1st call: LLM decides to use file_read
        AIMessage(
            content="",
            tool_calls=[{"name": "file_read", "args": {"path": "test.txt"}, "id": "call_1"}],
        ),
        # 2nd call: LLM responds after seeing tool result
        AIMessage(content="파일 내용은 hello world입니다."),
    ])

    checkpointer = MemorySaver()
    graph = create_agent(mock_llm, registry=safe_registry, checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "test-1"}}

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="test.txt 읽어줘")]},
        config,
    )

    assert result["messages"][-1].content == "파일 내용은 hello world입니다."
    # LLM was called twice (agent -> tool -> agent -> END)
    assert mock_llm.ainvoke.call_count == 2


@pytest.mark.asyncio
async def test_agent_no_tool_call_goes_to_end(mock_llm, safe_registry):
    mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="안녕하세요!"))

    checkpointer = MemorySaver()
    graph = create_agent(mock_llm, registry=safe_registry, checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "test-2"}}

    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="안녕")]},
        config,
    )

    assert result["messages"][-1].content == "안녕하세요!"
    assert mock_llm.ainvoke.call_count == 1
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_tools.py -v`
Expected: FAIL — `create_agent()` doesn't accept `registry` parameter yet

**Step 3: Rewrite agent.py with tool routing**

```python
# src/gp_claw/agent.py
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from gp_claw.tools.registry import ToolRegistry, ToolSafety


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    pending_tool_call: dict[str, Any] | None
    user_decision: str | None


def create_agent(
    llm: ChatOpenAI,
    registry: ToolRegistry | None = None,
    checkpointer=None,
):
    """에이전트 그래프 생성.

    Args:
        llm: LLM 인스턴스
        registry: ToolRegistry. None이면 도구 없는 단순 대화 모드.
        checkpointer: LangGraph 체크포인터
    """
    graph = StateGraph(AgentState)

    if registry is None:
        # Phase 1 호환: 단순 대화
        async def simple_agent(state: AgentState) -> dict:
            response = await llm.ainvoke(state["messages"])
            return {"messages": [response]}

        graph.add_node("agent", simple_agent)
        graph.set_entry_point("agent")
        graph.add_edge("agent", END)
        return graph.compile(checkpointer=checkpointer)

    # Phase 2+: 도구 라우팅 그래프
    llm_with_tools = llm.bind_tools(registry.all_tools)

    async def agent_node(state: AgentState) -> dict:
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    def route_tool_call(state: AgentState) -> str:
        last = state["messages"][-1]
        if not getattr(last, "tool_calls", None):
            return "end"
        for tc in last.tool_calls:
            if registry.classify(tc["name"]) == ToolSafety.DANGEROUS:
                return "dangerous"
        return "safe"

    graph.add_node("agent", agent_node)
    graph.add_node("safe_tools", ToolNode(registry.safe_tools))

    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route_tool_call, {
        "safe": "safe_tools",
        "dangerous": "approval",  # Task 7에서 구현
        "end": END,
    })
    graph.add_edge("safe_tools", "agent")

    # Phase 2C에서 approval/dangerous 노드 추가 전까지 placeholder
    if registry.dangerous_tools:
        from gp_claw.agent_approval import add_approval_nodes
        add_approval_nodes(graph, registry)

    return graph.compile(checkpointer=checkpointer)
```

> **주의**: 위 코드의 `approval` 경로와 `add_approval_nodes`는 Task 7에서 구현합니다.
> Task 3~5에서는 dangerous_tools가 없는 safe_registry로 테스트하므로 이 경로를 타지 않습니다.
> Task 7에서 `agent_approval.py`를 생성하면서 완성됩니다.

**실제 Task 3에서 작성할 agent.py** (Phase 2C 전까지의 임시 버전):

```python
# src/gp_claw/agent.py — Task 3 시점의 실제 코드
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from gp_claw.tools.registry import ToolRegistry, ToolSafety


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    pending_tool_call: dict[str, Any] | None
    user_decision: str | None


def create_agent(
    llm: ChatOpenAI,
    registry: ToolRegistry | None = None,
    checkpointer=None,
):
    graph = StateGraph(AgentState)

    if registry is None:
        async def simple_agent(state: AgentState) -> dict:
            response = await llm.ainvoke(state["messages"])
            return {"messages": [response]}

        graph.add_node("agent", simple_agent)
        graph.set_entry_point("agent")
        graph.add_edge("agent", END)
        return graph.compile(checkpointer=checkpointer)

    llm_with_tools = llm.bind_tools(registry.all_tools)

    async def agent_node(state: AgentState) -> dict:
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    def route_tool_call(state: AgentState) -> str:
        last = state["messages"][-1]
        if not getattr(last, "tool_calls", None):
            return "end"
        for tc in last.tool_calls:
            if registry.classify(tc["name"]) == ToolSafety.DANGEROUS:
                return "dangerous"
        return "safe"

    graph.add_node("agent", agent_node)
    graph.add_node("safe_tools", ToolNode(registry.safe_tools))

    graph.set_entry_point("agent")

    # dangerous 경로는 Phase 2C에서 추가. 현재는 safe/end만 활성.
    routes = {"safe": "safe_tools", "end": END}
    if registry.dangerous_tools:
        routes["dangerous"] = "approval"
    graph.add_conditional_edges("agent", route_tool_call, routes)
    graph.add_edge("safe_tools", "agent")

    return graph.compile(checkpointer=checkpointer)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_tools.py -v`
Expected: ALL PASS (4 tests)

**Step 5: Run all tests (기존 포함)**

Run: `pytest -v`
Expected: ALL PASS (기존 test_agent.py 포함 — `create_agent(mock_llm)` 호환)

**Step 6: Commit**

```bash
git add src/gp_claw/agent.py tests/test_agent_tools.py
git commit -m "feat: agent graph with safe tool routing (Phase 2B)"
```

---

### Task 4: WebSocket Tool Support + Entry Point Update

**Files:**
- Modify: `src/gp_claw/server.py`
- Modify: `src/gp_claw/__main__.py`
- Test: `tests/test_ws_agent.py` (기존 테스트 호환 확인)

**Step 1: Update server.py to accept registry**

```python
# src/gp_claw/server.py
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from gp_claw.agent import create_agent
from gp_claw.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


def create_app(
    llm: ChatOpenAI | None = None,
    registry: ToolRegistry | None = None,
) -> FastAPI:
    """FastAPI 애플리케이션 생성.

    Args:
        llm: LLM 인스턴스. None이면 에코 모드.
        registry: ToolRegistry. None이면 도구 없는 대화 모드.
    """
    app = FastAPI(title="GP Claw", version="0.2.0")
    checkpointer = MemorySaver()
    agent = create_agent(llm, registry=registry, checkpointer=checkpointer) if llm else None

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        await websocket.accept()
        logger.info(f"WebSocket connected: session={session_id}")
        config = {"configurable": {"thread_id": session_id}}

        try:
            while True:
                data = await websocket.receive_json()

                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})

                elif data.get("type") == "user_message":
                    content = data.get("content", "")

                    if agent:
                        result = await agent.ainvoke(
                            {"messages": [HumanMessage(content=content)]},
                            config,
                        )

                        # Phase 2C: interrupt 처리 (approval 루프)
                        state = await agent.aget_state(config)
                        while state.next:
                            interrupt_data = state.tasks[0].interrupts[0].value
                            await websocket.send_json({
                                "type": "approval_request",
                                **interrupt_data,
                            })

                            response = await websocket.receive_json()
                            if response.get("type") == "approval_response":
                                decision = response.get("decision", "rejected")
                            else:
                                decision = "rejected"

                            from langgraph.types import Command
                            result = await agent.ainvoke(
                                Command(resume=decision), config,
                            )
                            state = await agent.aget_state(config)

                        last_message = result["messages"][-1]
                        if hasattr(last_message, "content") and last_message.content:
                            await websocket.send_json({
                                "type": "assistant_message",
                                "content": last_message.content,
                            })
                    else:
                        await websocket.send_json({
                            "type": "assistant_message",
                            "content": f"[에코] {content}",
                        })

                else:
                    await websocket.send_json({
                        "type": "error",
                        "content": f"알 수 없는 메시지 타입: {data.get('type')}",
                    })

        except WebSocketDisconnect:
            logger.info(f"WebSocket disconnected: session={session_id}")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            await websocket.close(code=1011, reason=str(e))

    return app
```

**Step 2: Update entry point**

```python
# src/gp_claw/__main__.py
import uvicorn

from gp_claw.config import Settings
from gp_claw.llm import create_llm
from gp_claw.server import create_app
from gp_claw.tools import create_tool_registry


def main():
    settings = Settings()

    llm = None
    if settings.runpod_api_key and settings.runpod_endpoint_id:
        llm = create_llm(settings)
        print(f"LLM connected: {settings.vllm_model_name}")
    else:
        print("No LLM configured — running in echo mode")

    registry = create_tool_registry(str(settings.workspace_root))
    app = create_app(llm=llm, registry=registry)
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
```

**Step 3: Run existing tests to verify backward compatibility**

Run: `pytest tests/test_server.py tests/test_ws_agent.py -v`
Expected: ALL PASS (기존 테스트는 `create_app(llm=mock_llm)` → `registry=None` 기본값)

**Step 4: Run all tests**

Run: `pytest -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/gp_claw/server.py src/gp_claw/__main__.py
git commit -m "feat: server accepts ToolRegistry, entry point creates tools"
```

---

### Task 5: Integration Test — Safe Tool E2E

**Files:**
- Test: `tests/test_agent_tools.py` (추가)

**Step 1: Add E2E integration test**

`tests/test_agent_tools.py` 하단에 추가:

```python
@pytest.mark.asyncio
async def test_safe_tool_e2e_via_websocket(workspace):
    """WebSocket → Agent → Safe Tool → Response 전체 흐름."""
    from fastapi.testclient import TestClient
    from gp_claw.server import create_app
    from gp_claw.tools import create_tool_registry

    (workspace / "memo.txt").write_text("회의는 3시입니다")

    mock_llm = MagicMock()
    mock_llm.bind_tools = MagicMock(return_value=mock_llm)
    mock_llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(
            content="",
            tool_calls=[{"name": "file_read", "args": {"path": "memo.txt"}, "id": "c1"}],
        ),
        AIMessage(content="메모 내용: 회의는 3시입니다"),
    ])

    registry = create_tool_registry(str(workspace))
    # safe_tools만 등록 (dangerous 제외)
    from gp_claw.tools.registry import ToolRegistry
    safe_only = ToolRegistry(safe_tools=registry.safe_tools)

    app = create_app(llm=mock_llm, registry=safe_only)
    client = TestClient(app)

    with client.websocket_connect("/ws/e2e-test") as ws:
        ws.send_json({"type": "user_message", "content": "memo.txt 읽어줘"})
        data = ws.receive_json()
        assert data["type"] == "assistant_message"
        assert "회의는 3시" in data["content"]
```

**Step 2: Run the test**

Run: `pytest tests/test_agent_tools.py::test_safe_tool_e2e_via_websocket -v`
Expected: PASS

**Step 3: Run all tests**

Run: `pytest -v`
Expected: ALL PASS

**Step 4: Commit — Phase 2B 완료**

```bash
git add tests/test_agent_tools.py
git commit -m "feat(Phase 2B): agent-tool integration with safe tool E2E test"
```

---

## Phase 2C: Dangerous File Tools + Human-in-the-Loop

### Task 6: Dangerous File Tools (file_write, file_delete, file_move)

**Files:**
- Create: `src/gp_claw/tools/dangerous_file.py`
- Modify: `src/gp_claw/tools/__init__.py`
- Test: `tests/test_dangerous_file_tools.py`

**Step 1: Write the failing tests**

```python
# tests/test_dangerous_file_tools.py
import pytest

from gp_claw.tools.dangerous_file import create_dangerous_file_tools


@pytest.fixture
def tools(workspace):
    return create_dangerous_file_tools(str(workspace))


@pytest.fixture
def file_write(tools):
    return tools[0]


@pytest.fixture
def file_delete(tools):
    return tools[1]


@pytest.fixture
def file_move(tools):
    return tools[2]


# --- file_write ---

def test_file_write_creates_new_file(workspace, file_write):
    result = file_write.invoke({"path": "new.txt", "content": "hello"})
    assert result["action"] == "created"
    assert (workspace / "new.txt").read_text() == "hello"


def test_file_write_overwrites_existing(workspace, file_write):
    (workspace / "exist.txt").write_text("old")
    result = file_write.invoke({"path": "exist.txt", "content": "new"})
    assert result["action"] == "overwritten"
    assert (workspace / "exist.txt").read_text() == "new"


def test_file_write_creates_parent_dirs(workspace, file_write):
    result = file_write.invoke({"path": "sub/deep/file.txt", "content": "nested"})
    assert result["action"] == "created"
    assert (workspace / "sub" / "deep" / "file.txt").read_text() == "nested"


def test_file_write_blocks_outside_workspace(workspace, file_write):
    with pytest.raises(Exception):
        file_write.invoke({"path": "/etc/hacked", "content": "bad"})


# --- file_delete ---

def test_file_delete_removes_file(workspace, file_delete):
    target = workspace / "delete_me.txt"
    target.write_text("bye")
    result = file_delete.invoke({"path": "delete_me.txt"})
    assert not target.exists()
    assert result["size_bytes"] > 0


def test_file_delete_nonexistent_raises(workspace, file_delete):
    with pytest.raises(Exception):
        file_delete.invoke({"path": "no_such_file.txt"})


# --- file_move ---

def test_file_move_renames(workspace, file_move):
    (workspace / "old.txt").write_text("data")
    result = file_move.invoke({"source": "old.txt", "destination": "new.txt"})
    assert not (workspace / "old.txt").exists()
    assert (workspace / "new.txt").read_text() == "data"


def test_file_move_to_subdir(workspace, file_move):
    (workspace / "src.txt").write_text("data")
    result = file_move.invoke({"source": "src.txt", "destination": "sub/dst.txt"})
    assert (workspace / "sub" / "dst.txt").read_text() == "data"


def test_file_move_nonexistent_raises(workspace, file_move):
    with pytest.raises(Exception):
        file_move.invoke({"source": "ghost.txt", "destination": "dest.txt"})
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_dangerous_file_tools.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write minimal implementation**

```python
# src/gp_claw/tools/dangerous_file.py
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
```

Update `__init__.py`:

```python
# src/gp_claw/tools/__init__.py
from gp_claw.tools.registry import ToolRegistry, ToolSafety
from gp_claw.tools.safe_file import create_safe_file_tools
from gp_claw.tools.dangerous_file import create_dangerous_file_tools


def create_tool_registry(workspace_root: str) -> ToolRegistry:
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
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_dangerous_file_tools.py -v`
Expected: ALL PASS (10 tests)

**Step 5: Commit**

```bash
git add src/gp_claw/tools/dangerous_file.py src/gp_claw/tools/__init__.py tests/test_dangerous_file_tools.py
git commit -m "feat: dangerous file tools (file_write, file_delete, file_move)"
```

---

### Task 7: Approval Node + LangGraph Interrupt

**Files:**
- Modify: `src/gp_claw/agent.py` (approval/dangerous 노드 추가)
- Test: `tests/test_agent_tools.py` (approval 테스트 추가)

**Step 1: Write the failing tests**

`tests/test_agent_tools.py` 하단에 추가:

```python
from gp_claw.tools.dangerous_file import create_dangerous_file_tools
from langgraph.types import Command


@pytest.fixture
def full_registry(workspace):
    return ToolRegistry(
        safe_tools=create_safe_file_tools(str(workspace)),
        dangerous_tools=create_dangerous_file_tools(str(workspace)),
    )


@pytest.mark.asyncio
async def test_dangerous_tool_triggers_interrupt(workspace, mock_llm, full_registry):
    """Dangerous 도구 호출 시 interrupt 발생."""
    mock_llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(
            content="",
            tool_calls=[{
                "name": "file_write",
                "args": {"path": "out.txt", "content": "hello"},
                "id": "call_1",
            }],
        ),
        AIMessage(content="파일을 작성했습니다."),
    ])

    checkpointer = MemorySaver()
    graph = create_agent(mock_llm, registry=full_registry, checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "approval-test-1"}}

    # 첫 invoke: interrupt에서 멈춤
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content="out.txt에 hello 써줘")]},
        config,
    )

    state = await graph.aget_state(config)
    assert state.next  # 그래프가 중단됨 (pending nodes 있음)
    assert state.tasks[0].interrupts[0].value["type"] == "approval_request"


@pytest.mark.asyncio
async def test_approval_approved_executes_tool(workspace, mock_llm, full_registry):
    """승인 후 Dangerous 도구가 실행됨."""
    mock_llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(
            content="",
            tool_calls=[{
                "name": "file_write",
                "args": {"path": "out.txt", "content": "approved content"},
                "id": "call_1",
            }],
        ),
        AIMessage(content="파일을 작성했습니다."),
    ])

    checkpointer = MemorySaver()
    graph = create_agent(mock_llm, registry=full_registry, checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "approval-test-2"}}

    await graph.ainvoke(
        {"messages": [HumanMessage(content="out.txt에 써줘")]},
        config,
    )

    # 승인
    result = await graph.ainvoke(Command(resume="approved"), config)

    assert (workspace / "out.txt").read_text() == "approved content"
    assert result["messages"][-1].content == "파일을 작성했습니다."


@pytest.mark.asyncio
async def test_approval_rejected_skips_tool(workspace, mock_llm, full_registry):
    """거부 시 도구 실행 안 됨."""
    mock_llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(
            content="",
            tool_calls=[{
                "name": "file_write",
                "args": {"path": "out.txt", "content": "bad"},
                "id": "call_1",
            }],
        ),
        AIMessage(content="작업이 취소되었습니다."),
    ])

    checkpointer = MemorySaver()
    graph = create_agent(mock_llm, registry=full_registry, checkpointer=checkpointer)
    config = {"configurable": {"thread_id": "approval-test-3"}}

    await graph.ainvoke(
        {"messages": [HumanMessage(content="out.txt에 써줘")]},
        config,
    )

    # 거부
    result = await graph.ainvoke(Command(resume="rejected"), config)

    assert not (workspace / "out.txt").exists()  # 파일 생성 안 됨
    assert result["messages"][-1].content == "작업이 취소되었습니다."
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent_tools.py::test_dangerous_tool_triggers_interrupt -v`
Expected: FAIL — approval node not defined

**Step 3: Update agent.py with full graph**

```python
# src/gp_claw/agent.py
from typing import Annotated, Any

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from typing_extensions import TypedDict

from gp_claw.tools.registry import ToolRegistry, ToolSafety


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    pending_tool_call: dict[str, Any] | None
    user_decision: str | None


def _generate_preview(tool_call: dict) -> str:
    """승인 카드용 미리보기 텍스트 생성."""
    name = tool_call["name"]
    args = tool_call["args"]
    if name == "file_write":
        content = args.get("content", "")
        preview = content[:500]
        suffix = "..." if len(content) > 500 else ""
        return f"파일 쓰기: {args['path']}\n내용:\n{preview}{suffix}"
    if name == "file_delete":
        return f"파일 삭제: {args['path']}"
    if name == "file_move":
        return f"파일 이동: {args['source']} -> {args['destination']}"
    return f"{name}: {args}"


def create_agent(
    llm: ChatOpenAI,
    registry: ToolRegistry | None = None,
    checkpointer=None,
):
    graph = StateGraph(AgentState)

    # --- Phase 1 호환: 도구 없는 단순 대화 ---
    if registry is None:
        async def simple_agent(state: AgentState) -> dict:
            response = await llm.ainvoke(state["messages"])
            return {"messages": [response]}

        graph.add_node("agent", simple_agent)
        graph.set_entry_point("agent")
        graph.add_edge("agent", END)
        return graph.compile(checkpointer=checkpointer)

    # --- Phase 2+: 도구 라우팅 그래프 ---
    llm_with_tools = llm.bind_tools(registry.all_tools)

    async def agent_node(state: AgentState) -> dict:
        response = await llm_with_tools.ainvoke(state["messages"])
        return {"messages": [response]}

    def route_tool_call(state: AgentState) -> str:
        last = state["messages"][-1]
        if not getattr(last, "tool_calls", None):
            return "end"
        for tc in last.tool_calls:
            if registry.classify(tc["name"]) == ToolSafety.DANGEROUS:
                return "dangerous"
        return "safe"

    def approval_node(state: AgentState) -> dict:
        last = state["messages"][-1]
        previews = []
        for tc in last.tool_calls:
            previews.append({
                "tool": tc["name"],
                "args": tc["args"],
                "preview": _generate_preview(tc),
            })
        decision = interrupt({
            "type": "approval_request",
            "tool_calls": previews,
        })
        return {"user_decision": decision}

    def route_approval(state: AgentState) -> str:
        if state.get("user_decision") == "approved":
            return "approved"
        return "rejected"

    def handle_rejection(state: AgentState) -> dict:
        last = state["messages"][-1]
        rejections = []
        for tc in last.tool_calls:
            rejections.append(
                ToolMessage(
                    content=f"사용자가 {tc['name']} 실행을 거부했습니다.",
                    tool_call_id=tc["id"],
                )
            )
        return {"messages": rejections, "user_decision": None}

    # 노드 등록
    graph.add_node("agent", agent_node)
    graph.add_node("safe_tools", ToolNode(registry.safe_tools))
    graph.add_node("approval", approval_node)
    graph.add_node("dangerous_tools", ToolNode(registry.all_tools))
    graph.add_node("handle_rejection", handle_rejection)

    # 엣지
    graph.set_entry_point("agent")
    graph.add_conditional_edges("agent", route_tool_call, {
        "safe": "safe_tools",
        "dangerous": "approval",
        "end": END,
    })
    graph.add_edge("safe_tools", "agent")
    graph.add_conditional_edges("approval", route_approval, {
        "approved": "dangerous_tools",
        "rejected": "handle_rejection",
    })
    graph.add_edge("dangerous_tools", "agent")
    graph.add_edge("handle_rejection", "agent")

    return graph.compile(checkpointer=checkpointer)
```

**Step 4: Run test to verify it passes**

Run: `pytest tests/test_agent_tools.py -v`
Expected: ALL PASS (기존 4 + 신규 3 = 7 tests)

**Step 5: Run all tests**

Run: `pytest -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add src/gp_claw/agent.py tests/test_agent_tools.py
git commit -m "feat: approval node with LangGraph interrupt for dangerous tools"
```

---

### Task 8: WebSocket Approval Protocol Integration Test

**Files:**
- Test: `tests/test_ws_approval.py`

**Step 1: Write integration tests**

```python
# tests/test_ws_approval.py
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from gp_claw.server import create_app
from gp_claw.tools import create_tool_registry
from gp_claw.tools.registry import ToolRegistry


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.bind_tools = MagicMock(return_value=llm)
    return llm


def test_ws_dangerous_tool_sends_approval_request(workspace, mock_llm):
    """Dangerous 도구 호출 시 WebSocket으로 approval_request 전송."""
    mock_llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(
            content="",
            tool_calls=[{
                "name": "file_write",
                "args": {"path": "test.txt", "content": "hello"},
                "id": "call_1",
            }],
        ),
        AIMessage(content="파일을 작성했습니다."),
    ])

    registry = create_tool_registry(str(workspace))
    app = create_app(llm=mock_llm, registry=registry)
    client = TestClient(app)

    with client.websocket_connect("/ws/approval-ws-1") as ws:
        ws.send_json({"type": "user_message", "content": "test.txt에 hello 써줘"})

        # 승인 요청 수신
        data = ws.receive_json()
        assert data["type"] == "approval_request"
        assert data["tool_calls"][0]["tool"] == "file_write"

        # 승인
        ws.send_json({"type": "approval_response", "decision": "approved"})

        # 최종 응답
        data = ws.receive_json()
        assert data["type"] == "assistant_message"
        assert "작성" in data["content"]

    # 파일이 실제로 생성되었는지 확인
    assert (workspace / "test.txt").read_text() == "hello"


def test_ws_dangerous_tool_rejection(workspace, mock_llm):
    """거부 시 도구 실행 안 되고 거부 메시지 전달."""
    mock_llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(
            content="",
            tool_calls=[{
                "name": "file_delete",
                "args": {"path": "important.txt"},
                "id": "call_1",
            }],
        ),
        AIMessage(content="알겠습니다. 삭제를 취소합니다."),
    ])

    (workspace / "important.txt").write_text("keep me")
    registry = create_tool_registry(str(workspace))
    app = create_app(llm=mock_llm, registry=registry)
    client = TestClient(app)

    with client.websocket_connect("/ws/approval-ws-2") as ws:
        ws.send_json({"type": "user_message", "content": "important.txt 삭제해줘"})

        data = ws.receive_json()
        assert data["type"] == "approval_request"

        ws.send_json({"type": "approval_response", "decision": "rejected"})

        data = ws.receive_json()
        assert data["type"] == "assistant_message"
        assert "취소" in data["content"]

    # 파일이 삭제되지 않았는지 확인
    assert (workspace / "important.txt").exists()


def test_ws_safe_tool_no_approval_needed(workspace, mock_llm):
    """Safe 도구는 승인 없이 바로 실행."""
    (workspace / "doc.txt").write_text("내용입니다")

    mock_llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(
            content="",
            tool_calls=[{
                "name": "file_read",
                "args": {"path": "doc.txt"},
                "id": "call_1",
            }],
        ),
        AIMessage(content="파일 내용: 내용입니다"),
    ])

    registry = create_tool_registry(str(workspace))
    app = create_app(llm=mock_llm, registry=registry)
    client = TestClient(app)

    with client.websocket_connect("/ws/approval-ws-3") as ws:
        ws.send_json({"type": "user_message", "content": "doc.txt 읽어줘"})

        # 승인 요청 없이 바로 응답
        data = ws.receive_json()
        assert data["type"] == "assistant_message"
        assert "내용입니다" in data["content"]
```

**Step 2: Run tests**

Run: `pytest tests/test_ws_approval.py -v`
Expected: ALL PASS (3 tests)

**Step 3: Run all tests**

Run: `pytest -v`
Expected: ALL PASS (전체)

**Step 4: Commit — Phase 2C 완료**

```bash
git add tests/test_ws_approval.py tests/test_agent_tools.py tests/test_dangerous_file_tools.py
git commit -m "feat(Phase 2): tool system + HITL approval workflow complete"
```

---

## 최종 그래프 토폴로지

```
START -> agent -> route_tool_call
    -> "end" -> END
    -> "safe" -> safe_tools -> agent
    -> "dangerous" -> approval -> route_approval
        -> "approved" -> dangerous_tools -> agent
        -> "rejected" -> handle_rejection -> agent
```

## WebSocket 프로토콜 (Phase 2 확장)

| 방향 | type | 설명 |
|------|------|------|
| Client → Server | `user_message` | 사용자 메시지 |
| Client → Server | `approval_response` | `{"decision": "approved"\|"rejected"}` |
| Client → Server | `ping` | 연결 확인 |
| Server → Client | `assistant_message` | 에이전트 응답 |
| Server → Client | `approval_request` | `{"tool_calls": [{tool, args, preview}]}` |
| Server → Client | `pong` | 연결 확인 응답 |
| Server → Client | `error` | 에러 메시지 |

## 테스트 요약

| 파일 | 테스트 수 | 범위 |
|------|----------|------|
| `test_tool_registry.py` | 5 | ToolSafety, ToolRegistry |
| `test_safe_file_tools.py` | 6 | file_read, file_search, file_list |
| `test_dangerous_file_tools.py` | 10 | file_write, file_delete, file_move |
| `test_agent_tools.py` | 8 | 그래프 라우팅, safe/dangerous 분기, E2E |
| `test_ws_approval.py` | 3 | WebSocket 승인 프로토콜 |
| 기존 Phase 1 | 16 | config, llm, security, agent, server |
| **합계** | **~48** | |
