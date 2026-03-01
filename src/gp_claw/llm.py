import json
import re
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

from gp_claw.config import Settings


def _build_tools_system_prompt(tools: list) -> str:
    """도구 정의를 시스템 프롬프트 텍스트로 변환."""
    tool_descs = []
    for tool in tools:
        schema = tool.args_schema.schema() if hasattr(tool, "args_schema") else {}
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        params = {}
        for name, prop in properties.items():
            params[name] = {
                "type": prop.get("type", "string"),
                "description": prop.get("description", ""),
            }

        tool_descs.append({
            "name": tool.name,
            "description": tool.description,
            "parameters": {
                "type": "object",
                "properties": params,
                "required": required,
            },
        })

    tools_json = json.dumps(tool_descs, ensure_ascii=False, indent=2)
    return f"""You are GP Claw, an AI office assistant that manages files in the user's workspace.

Available tools:
{tools_json}

IMPORTANT RULES:
- The workspace root is ".". All file paths are relative to the workspace root.
- For file_list and file_search, use "." as the directory to list the workspace root.
- NEVER use descriptive Korean text as path arguments. Use actual paths like ".", "reports", "data/test.txt".
- To use a tool, respond EXACTLY in this format:
<tool_call>{{"name": "tool_name", "arguments": {{"param": "value"}}}}</tool_call>
- You can make multiple tool calls in one response.
- Always respond in Korean."""


def _parse_tool_calls(content: str) -> tuple[str, list[dict]]:
    """응답 content에서 <tool_call> 태그를 파싱하여 tool_calls 리스트로 변환."""
    pattern = r"<tool_call>(.*?)</tool_call>"
    matches = re.findall(pattern, content, re.DOTALL)

    tool_calls = []
    for match in matches:
        try:
            parsed = json.loads(match.strip())
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "name": parsed["name"],
                "args": parsed.get("arguments", {}),
            })
        except (json.JSONDecodeError, KeyError):
            continue

    # tool_call 태그를 제거한 나머지 텍스트
    clean_content = re.sub(pattern, "", content, flags=re.DOTALL).strip()
    return clean_content, tool_calls


class ToolParsingChatModel(ChatOpenAI):
    """<tool_call> 태그를 파싱하여 tool_calls로 변환하는 ChatOpenAI 래퍼.

    vLLM의 tool-call-parser가 작동하지 않을 때 사용.
    bind_tools() 대신 시스템 프롬프트로 도구를 주입하고,
    응답의 <tool_call> 태그를 파싱합니다.
    """

    _tools_system_prompt: str = ""
    _bound_tools: list = []

    class Config:
        arbitrary_types_allowed = True

    def bind_tools(self, tools: list, **kwargs) -> "ToolParsingChatModel":
        """도구를 바인딩 (실제로는 시스템 프롬프트로 변환)."""
        clone = self.model_copy()
        clone._tools_system_prompt = _build_tools_system_prompt(tools)
        clone._bound_tools = tools
        return clone

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        # 시스템 프롬프트 주입
        if self._tools_system_prompt:
            kwargs.pop("tools", None)
            kwargs.pop("tool_choice", None)
            has_system = any(isinstance(m, SystemMessage) for m in messages)
            if not has_system:
                messages = [SystemMessage(content=self._tools_system_prompt)] + list(messages)

        result = super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)

        # <tool_call> 태그 파싱
        for gen in result.generations:
            msg = gen.message
            if isinstance(msg, AIMessage) and msg.content:
                clean_content, tool_calls = _parse_tool_calls(msg.content)
                if tool_calls:
                    msg.content = clean_content
                    msg.tool_calls = tool_calls
                    msg.additional_kwargs["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"], ensure_ascii=False),
                            },
                        }
                        for tc in tool_calls
                    ]

        return result

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        # 시스템 프롬프트 주입
        if self._tools_system_prompt:
            kwargs.pop("tools", None)
            kwargs.pop("tool_choice", None)
            has_system = any(isinstance(m, SystemMessage) for m in messages)
            if not has_system:
                messages = [SystemMessage(content=self._tools_system_prompt)] + list(messages)

        result = await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)

        # <tool_call> 태그 파싱
        for gen in result.generations:
            msg = gen.message
            if isinstance(msg, AIMessage) and msg.content:
                clean_content, tool_calls = _parse_tool_calls(msg.content)
                if tool_calls:
                    msg.content = clean_content
                    msg.tool_calls = tool_calls
                    msg.additional_kwargs["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc["args"], ensure_ascii=False),
                            },
                        }
                        for tc in tool_calls
                    ]

        return result

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """스트리밍 + 시스템 프롬프트 주입 + tool_call 파싱."""
        # 시스템 프롬프트 주입
        if self._tools_system_prompt:
            kwargs.pop("tools", None)
            kwargs.pop("tool_choice", None)
            has_system = any(isinstance(m, SystemMessage) for m in messages)
            if not has_system:
                messages = [SystemMessage(content=self._tools_system_prompt)] + list(messages)

        # 청크를 모으면서 스트리밍
        full_content = ""
        async for chunk in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
            if isinstance(chunk.message, AIMessageChunk) and chunk.message.content:
                full_content += chunk.message.content
            yield chunk

        # 스트리밍 완료 후 tool_call 파싱
        if full_content:
            _, tool_calls = _parse_tool_calls(full_content)
            if tool_calls:
                tc_msg = AIMessageChunk(
                    content="",
                    tool_call_chunks=[
                        {
                            "id": tc["id"],
                            "name": tc["name"],
                            "args": json.dumps(tc["args"], ensure_ascii=False),
                            "index": i,
                        }
                        for i, tc in enumerate(tool_calls)
                    ],
                )
                yield ChatGenerationChunk(message=tc_msg)


def create_llm(settings: Settings) -> ToolParsingChatModel:
    """RunPod vLLM 엔드포인트에 연결하는 LLM 인스턴스 생성."""
    return ToolParsingChatModel(
        model=settings.vllm_model_name,
        api_key=settings.runpod_api_key,
        base_url=settings.vllm_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        streaming=True,
    )
