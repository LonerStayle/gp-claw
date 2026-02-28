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

    # dangerous 경로는 Phase 2C에서 추가. 현재는 safe/end만 활성.
    routes = {"safe": "safe_tools", "end": END}
    if registry.dangerous_tools:
        routes["dangerous"] = "approval"
    graph.add_conditional_edges("agent", route_tool_call, routes)
    graph.add_edge("safe_tools", "agent")

    return graph.compile(checkpointer=checkpointer)
