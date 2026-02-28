from unittest.mock import MagicMock

from gp_claw.agent import create_agent, AgentState


def test_agent_state_has_required_fields():
    """AgentState에 필수 필드가 있는지 확인."""
    state = AgentState(messages=[], pending_tool_call=None, user_decision=None)
    assert state["messages"] == []
    assert state["pending_tool_call"] is None


def test_create_agent_returns_compiled_graph():
    """create_agent가 컴파일된 그래프를 반환하는지 확인."""
    mock_llm = MagicMock()
    graph = create_agent(mock_llm)
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "stream")


def test_create_agent_has_expected_nodes():
    """그래프에 필수 노드가 있는지 확인."""
    mock_llm = MagicMock()
    graph = create_agent(mock_llm)
    node_names = set(graph.get_graph().nodes.keys())
    assert "agent" in node_names
