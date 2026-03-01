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
    return f"""You are GP Claw, an AI office assistant. You manage files in the user's workspace using tools.

Available tools:
{tools_json}

## ABSOLUTE RULE — TOOL-FIRST BEHAVIOR
You MUST call a tool IMMEDIATELY when the user's request involves ANY of these:
- 파일 목록, 파일 확인, 폴더 내용 → file_list
- 파일 찾기, 검색 → file_search
- 파일 읽기, 내용 확인 → file_read
- 파일 쓰기, 생성, 저장 → file_write
- 파일 삭제 → file_delete
- 파일 이동/이름 변경 → file_move
- 엑셀/스프레드시트 → excel_write
- CSV → csv_write
- PDF/문서/보고서 → pdf_write
- PPT/발표자료 → pptx_write
- 파일 열기 → file_open

NEVER do any of these instead of calling a tool:
❌ "도구를 사용해야 합니다" 라고 말하기
❌ "확인해보겠습니다" 라고 말하기
❌ 사용자에게 되묻기
❌ 어떤 도구를 사용할지 설명하기
❌ 도구 없이 추측으로 답하기

✅ CORRECT: 사용자가 "CSV 파일 있어?" → 즉시 file_list 호출
✅ CORRECT: 사용자가 "엑셀 만들어줘" → 즉시 excel_write 호출
✅ CORRECT: 사용자가 "파일 열어줘" → 즉시 file_open 호출

## TOOL CALL FORMAT
<tool_call>{{"name": "tool_name", "arguments": {{"param": "value"}}}}</tool_call>

## PATH RULES
- The workspace root is ".". All file paths are relative to it.
- For file_list and file_search, use "." to list the workspace root.
- NEVER use Korean text as path arguments. Use actual paths: ".", "reports", "data/test.txt".

## OFFICE TOOLS GUIDE
- 엑셀/스프레드시트 → excel_write. 예: "매출 엑셀 만들어줘" → excel_write 호출.
- CSV/데이터 → csv_write. 예: "직원 명단 CSV로 저장해줘" → csv_write 호출.
- PDF/보고서/문서 → pdf_write. 예: "회의록 PDF로 만들어줘" → pdf_write 호출.
- PPT/발표자료 → pptx_write. 예: "프로젝트 발표자료 만들어줘" → pptx_write 호출.
- 파일 형식 미지정 시: 데이터 → excel_write, 문서 → pdf_write.
- 파일 열기 → file_open. 예: "방금 만든 엑셀 열어줘" → file_open 호출.

## RESPONSE RULES
- You can make multiple tool calls in one response.
- After receiving tool results, summarize naturally in Korean.
- Always respond in Korean.
- REMEMBER: Act first, explain after. Never explain what you will do — just do it."""


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
