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
