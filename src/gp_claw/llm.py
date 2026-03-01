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
    return f"""당신은 GP Claw, 사무용 AI 비서입니다. 사용자가 파일 관련 요청을 하면 반드시 도구를 호출해야 합니다.
절대로 도구 호출 없이 텍스트로만 답하지 마세요.

사용 가능한 도구:
{tools_json}

도구 호출 형식:
<tool_call>{{"name": "도구이름", "arguments": {{"파라미터": "값"}}}}</tool_call>

예시:

사용자: 현재 폴더에 뭐 있어?
응답: <tool_call>{{"name": "file_list", "arguments": {{"directory": "."}}}}</tool_call>

사용자: CSV 파일 있어?
응답: <tool_call>{{"name": "file_list", "arguments": {{"directory": "."}}}}</tool_call>

사용자: test.txt 읽어줘
응답: <tool_call>{{"name": "file_read", "arguments": {{"path": "test.txt"}}}}</tool_call>

사용자: 매출 엑셀 만들어줘
응답: <tool_call>{{"name": "excel_write", "arguments": {{"path": "매출.xlsx", "sheets": [{{"name": "매출", "headers": ["항목", "금액"], "rows": [["매출1", 1000]]}}]}}}}</tool_call>

사용자: 파일 열어줘
응답: <tool_call>{{"name": "file_open", "arguments": {{"path": "매출.xlsx"}}}}</tool_call>

규칙:
- 파일 관련 요청에는 반드시 <tool_call>로 응답하세요.
- "도구를 사용해야 합니다", "확인해보겠습니다" 같은 텍스트 응답은 금지입니다.
- 경로는 항상 ".", "reports/data.csv" 같은 실제 경로를 사용하세요.
- 파일 형식 미지정 시: 데이터 → excel_write, 문서 → pdf_write.
- 도구 결과를 받으면 한국어로 자연스럽게 요약하세요.
- 항상 한국어로 답하세요. 생각(<think>)도 반드시 한국어로 하세요.
- 절대로 영어, 힌디어 등 다른 언어를 사용하지 마세요. 모든 출력은 한국어입니다."""


def _parse_tool_calls(content: str) -> tuple[str, list[dict]]:
    """응답 content에서 <tool_call> 태그를 파싱하여 tool_calls 리스트로 변환.

    닫는 태그(</tool_call>)가 없는 경우도 처리합니다.
    """
    # 1) 닫는 태그가 있는 경우
    pattern_closed = r"<tool_call>(.*?)</tool_call>"
    # 2) 닫는 태그 없이 <tool_call> 이후 끝까지
    pattern_open = r"<tool_call>(.*?)$"

    matches = re.findall(pattern_closed, content, re.DOTALL)
    clean_content = re.sub(pattern_closed, "", content, flags=re.DOTALL).strip()

    # 닫는 태그 매치가 없으면 열린 태그로 시도
    if not matches:
        matches = re.findall(pattern_open, content, re.DOTALL)
        clean_content = re.sub(pattern_open, "", content, flags=re.DOTALL).strip()

    tool_calls = []
    seen = set()
    for match in matches:
        try:
            parsed = json.loads(match.strip())
            # 중복 tool call 제거 (같은 이름+인자 조합)
            dedup_key = (parsed["name"], json.dumps(parsed.get("arguments", {}), sort_keys=True))
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            tool_calls.append({
                "id": f"call_{uuid.uuid4().hex[:8]}",
                "name": parsed["name"],
                "args": parsed.get("arguments", {}),
            })
        except (json.JSONDecodeError, KeyError):
            continue

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
        has_native_tool_calls = False
        async for chunk in super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs):
            if isinstance(chunk.message, AIMessageChunk):
                if chunk.message.content:
                    full_content += chunk.message.content
                if chunk.message.tool_call_chunks:
                    has_native_tool_calls = True
            yield chunk

        # 스트리밍 완료 후 tool_call 파싱 (네이티브 tool_call이 없을 때만)
        if full_content and not has_native_tool_calls:
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
        timeout=120,  # RunPod 콜드 스타트 (~74초) 대응
    )
