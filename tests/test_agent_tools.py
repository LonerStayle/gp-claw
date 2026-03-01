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
    safe_only = ToolRegistry(safe_tools=registry.safe_tools)

    app = create_app(llm=mock_llm, registry=safe_only)
    client = TestClient(app)

    with client.websocket_connect("/ws/e2e-test") as ws:
        ws.send_json({"type": "user_message", "content": "memo.txt 읽어줘"})
        data = ws.receive_json()
        assert data["type"] == "assistant_chunk"
        assert "회의는 3시" in data["content"]
        done = ws.receive_json()
        assert done["type"] == "assistant_done"


# --- Phase 2C: Approval tests ---

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
