from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    pending_tool_call: dict[str, Any] | None
    user_decision: str | None


def _call_llm(llm: ChatOpenAI):
    """LLM 호출 노드 팩토리."""
    async def node(state: AgentState) -> dict:
        response = await llm.ainvoke(state["messages"])
        return {"messages": [response]}
    return node


def create_agent(llm: ChatOpenAI, checkpointer=None):
    """기본 대화 에이전트 그래프 생성.

    Phase 1: 단순 LLM 대화만 지원.
    Phase 2+에서 도구, 승인, 서브에이전트 추가.
    """
    graph = StateGraph(AgentState)
    graph.add_node("agent", _call_llm(llm))
    graph.set_entry_point("agent")
    graph.add_edge("agent", END)

    return graph.compile(checkpointer=checkpointer)
