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
    """에이전트 그래프 생성.

    Args:
        llm: LLM 인스턴스
        registry: ToolRegistry. None이면 도구 없는 단순 대화 모드.
        checkpointer: LangGraph 체크포인터
    """
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
