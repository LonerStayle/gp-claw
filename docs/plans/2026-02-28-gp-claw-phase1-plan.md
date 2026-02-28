# GP Claw Phase 1: Foundation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 백엔드 기반 구축 — 프로젝트 세팅, RunPod vLLM 클라이언트, 기본 LangGraph 에이전트, FastAPI WebSocket 서버를 만들어 사용자가 웹소켓으로 AI와 대화할 수 있는 최소 동작 시스템을 완성한다.

**Architecture:** FastAPI WebSocket 서버가 LangGraph 에이전트를 구동하고, LangGraph는 RunPod vLLM 엔드포인트의 A.X 4.0 모델과 통신한다. 7B/72B 라우팅, 서브에이전트, 메모리는 Phase 2+에서 추가한다. Phase 1에서는 단일 모델 엔드포인트로 동작하는 기본 대화 시스템을 만든다.

**Tech Stack:** Python 3.11+, FastAPI, LangGraph, langchain-openai, uvicorn, pytest, SQLite (checkpointer)

**Design Doc:** `docs/plans/2026-02-28-gp-claw-design.md`

---

### Task 1: 프로젝트 스캐폴딩

**Files:**
- Create: `pyproject.toml`
- Create: `src/gp_claw/__init__.py`
- Create: `src/gp_claw/config.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `.env.example`
- Create: `.gitignore`

**Step 1: pyproject.toml 작성**

```toml
[project]
name = "gp-claw"
version = "0.1.0"
description = "회사 내부 AI 사무 비서"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "websockets>=12.0",
    "langgraph>=0.2.70",
    "langchain-openai>=0.3",
    "langgraph-checkpoint-sqlite>=2.0",
    "pydantic>=2.0",
    "pydantic-settings>=2.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "httpx>=0.27",
    "ruff>=0.6",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.ruff]
target-version = "py311"
line-length = 100
```

**Step 2: .gitignore 작성**

```
__pycache__/
*.pyc
.env
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
.ruff_cache/
*.sqlite
*.sqlite-journal
```

**Step 3: .env.example 작성**

```bash
# RunPod vLLM Configuration
RUNPOD_API_KEY=your_runpod_api_key
RUNPOD_ENDPOINT_ID=your_endpoint_id
VLLM_MODEL_NAME=your_model_name

# Server Configuration
HOST=0.0.0.0
PORT=8000
WORKSPACE_ROOT=~/.gp_claw/workspace
```

**Step 4: config.py 작성**

```python
from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # RunPod vLLM
    runpod_api_key: str = ""
    runpod_endpoint_id: str = ""
    vllm_model_name: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workspace_root: Path = Path.home() / ".gp_claw" / "workspace"

    # LLM
    llm_temperature: float = 0.6
    llm_max_tokens: int = 4096

    @property
    def vllm_base_url(self) -> str:
        return f"https://api.runpod.ai/v2/{self.runpod_endpoint_id}/openai/v1"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}
```

**Step 5: __init__.py 파일 생성**

```python
# src/gp_claw/__init__.py
```

```python
# tests/__init__.py
```

**Step 6: tests/conftest.py 작성**

```python
import pytest

from gp_claw.config import Settings


@pytest.fixture
def settings():
    return Settings(
        runpod_api_key="test-key",
        runpod_endpoint_id="test-endpoint",
        vllm_model_name="test-model",
        workspace_root="/tmp/gp_claw_test",
    )
```

**Step 7: 의존성 설치 및 확인**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
Expected: 성공적으로 설치

**Step 8: Commit**

```bash
git add pyproject.toml src/ tests/ .env.example .gitignore
git commit -m "chore: 프로젝트 스캐폴딩 — FastAPI + LangGraph + 기본 설정"
```

---

### Task 2: Settings 테스트

**Files:**
- Create: `tests/test_config.py`
- Verify: `src/gp_claw/config.py`

**Step 1: 테스트 작성**

```python
from pathlib import Path

from gp_claw.config import Settings


def test_settings_defaults():
    s = Settings(
        runpod_api_key="key",
        runpod_endpoint_id="ep-123",
        vllm_model_name="model-name",
    )
    assert s.host == "0.0.0.0"
    assert s.port == 8000
    assert s.llm_temperature == 0.6


def test_vllm_base_url():
    s = Settings(
        runpod_api_key="key",
        runpod_endpoint_id="ep-123",
        vllm_model_name="model-name",
    )
    assert s.vllm_base_url == "https://api.runpod.ai/v2/ep-123/openai/v1"


def test_workspace_root_default():
    s = Settings(
        runpod_api_key="key",
        runpod_endpoint_id="ep-123",
        vllm_model_name="model-name",
    )
    assert s.workspace_root == Path.home() / ".gp_claw" / "workspace"
```

**Step 2: 테스트 실행**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/test_config.py -v`
Expected: 3 PASSED

**Step 3: Commit**

```bash
git add tests/test_config.py
git commit -m "test: Settings 설정 테스트 추가"
```

---

### Task 3: LLM 클라이언트 래퍼

**Files:**
- Create: `src/gp_claw/llm.py`
- Create: `tests/test_llm.py`

**Step 1: 테스트 작성**

```python
from unittest.mock import patch

from gp_claw.config import Settings
from gp_claw.llm import create_llm


def test_create_llm_returns_chat_openai():
    settings = Settings(
        runpod_api_key="test-key",
        runpod_endpoint_id="ep-123",
        vllm_model_name="test-model",
    )
    llm = create_llm(settings)

    assert llm.model_name == "test-model"
    assert llm.openai_api_key.get_secret_value() == "test-key"
    assert "ep-123" in str(llm.openai_api_base)


def test_create_llm_uses_settings_temperature():
    settings = Settings(
        runpod_api_key="test-key",
        runpod_endpoint_id="ep-123",
        vllm_model_name="test-model",
        llm_temperature=0.3,
    )
    llm = create_llm(settings)
    assert llm.temperature == 0.3
```

**Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/test_llm.py -v`
Expected: FAIL — `ImportError: cannot import name 'create_llm'`

**Step 3: 구현**

```python
# src/gp_claw/llm.py
from langchain_openai import ChatOpenAI

from gp_claw.config import Settings


def create_llm(settings: Settings) -> ChatOpenAI:
    """RunPod vLLM 엔드포인트에 연결하는 ChatOpenAI 인스턴스 생성."""
    return ChatOpenAI(
        model=settings.vllm_model_name,
        api_key=settings.runpod_api_key,
        base_url=settings.vllm_base_url,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
```

**Step 4: 테스트 실행 — 성공 확인**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/test_llm.py -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add src/gp_claw/llm.py tests/test_llm.py
git commit -m "feat: RunPod vLLM LLM 클라이언트 래퍼 추가"
```

---

### Task 4: 서브에이전트 보안 프롬프트 모듈

**Files:**
- Create: `src/gp_claw/security.py`
- Create: `tests/test_security.py`

**Step 1: 테스트 작성**

```python
from gp_claw.security import SUBAGENT_SECURITY_PROMPT, validate_path, SecurityViolation

import pytest


def test_security_prompt_contains_key_rules():
    assert "경로 제한" in SUBAGENT_SECURITY_PROMPT
    assert "명령어 실행 금지" in SUBAGENT_SECURITY_PROMPT
    assert "데이터 유출 방지" in SUBAGENT_SECURITY_PROMPT
    assert "입력 검증" in SUBAGENT_SECURITY_PROMPT
    assert "최소 권한" in SUBAGENT_SECURITY_PROMPT
    assert "Dangerous 작업 금지" in SUBAGENT_SECURITY_PROMPT


def test_validate_path_allows_workspace_paths(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "test.txt"
    target.touch()
    # Should not raise
    result = validate_path(str(target), str(workspace))
    assert result == target


def test_validate_path_blocks_traversal(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(SecurityViolation, match="작업 디렉토리 외부"):
        validate_path("../../../etc/passwd", str(workspace))


def test_validate_path_blocks_system_paths(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(SecurityViolation, match="시스템 경로"):
        validate_path("/etc/passwd", str(workspace))


def test_validate_path_blocks_dotfiles(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    with pytest.raises(SecurityViolation, match="시스템 경로"):
        validate_path(str(workspace / ".ssh" / "id_rsa"), str(workspace))
```

**Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/test_security.py -v`
Expected: FAIL — `ImportError`

**Step 3: 구현**

```python
# src/gp_claw/security.py
from pathlib import Path


class SecurityViolation(Exception):
    """보안 규칙 위반 시 발생하는 예외."""


SUBAGENT_SECURITY_PROMPT = """[보안 규칙 - 반드시 준수]

1. 경로 제한: 허용된 작업 디렉토리(WORKSPACE_ROOT) 외부의 파일에 절대 접근하지 마세요.
   시스템 파일(/etc, /usr, ~/.ssh, ~/.env 등)에 접근을 시도하지 마세요.

2. 명령어 실행 금지: 쉘 명령어를 직접 실행하지 마세요.
   모든 작업은 제공된 도구 함수만 사용하세요.

3. 데이터 유출 방지: 파일 내용, 사용자 데이터, 회사 정보를 외부로 전송하지 마세요.
   도구 실행 결과에 불필요한 원본 데이터를 포함하지 마세요.
   결과는 요청된 작업의 결과만 최소한으로 반환하세요.

4. 입력 검증: 사용자 입력에 포함된 경로, 파일명, 이메일 주소를 검증하세요.
   경로 순회 공격(../ 등)을 차단하세요.
   의심스러운 입력은 거부하고 이유를 보고하세요.

5. 최소 권한 원칙: 작업에 필요한 최소한의 데이터만 읽으세요.
   작업 완료 후 임시 데이터를 정리하세요.

6. Dangerous 작업 금지: 서브에이전트는 Dangerous 등급 도구를 직접 실행할 수 없습니다.
   파일 삭제/수정, Gmail 발송 등은 메인 에이전트의 승인 흐름을 통해서만 실행됩니다.
   Dangerous 작업이 필요한 경우, 작업 내용을 메인 에이전트에 반환하여 승인을 요청하세요."""

BLOCKED_PREFIXES = ("/etc", "/usr", "/var", "/sys", "/proc", "/dev")
BLOCKED_DOTDIRS = (".ssh", ".env", ".aws", ".config", ".gnupg")


def validate_path(path_str: str, workspace_root: str) -> Path:
    """경로가 워크스페이스 내부인지 검증. 위반 시 SecurityViolation 발생."""
    workspace = Path(workspace_root).resolve()
    target = (workspace / path_str).resolve() if not Path(path_str).is_absolute() else Path(path_str).resolve()

    # 시스템 경로 차단
    target_str = str(target)
    for prefix in BLOCKED_PREFIXES:
        if target_str.startswith(prefix):
            raise SecurityViolation(f"시스템 경로 접근 차단: {target_str}")

    # 위험한 dotfile 디렉토리 차단
    for part in target.parts:
        if part in BLOCKED_DOTDIRS:
            raise SecurityViolation(f"시스템 경로 접근 차단: {target_str} ({part})")

    # 워크스페이스 외부 차단
    try:
        target.relative_to(workspace)
    except ValueError:
        raise SecurityViolation(f"작업 디렉토리 외부 접근 차단: {target_str}")

    return target
```

**Step 4: 테스트 실행 — 성공 확인**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/test_security.py -v`
Expected: 5 PASSED

**Step 5: Commit**

```bash
git add src/gp_claw/security.py tests/test_security.py
git commit -m "feat: 서브에이전트 보안 프롬프트 및 경로 검증 모듈 추가"
```

---

### Task 5: 기본 LangGraph 에이전트

**Files:**
- Create: `src/gp_claw/agent.py`
- Create: `tests/test_agent.py`

**Step 1: 테스트 작성**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
    # 컴파일된 그래프는 invoke/stream 메서드를 가짐
    assert hasattr(graph, "invoke")
    assert hasattr(graph, "stream")


def test_create_agent_has_expected_nodes():
    """그래프에 필수 노드가 있는지 확인."""
    mock_llm = MagicMock()
    graph = create_agent(mock_llm)
    node_names = set(graph.get_graph().nodes.keys())
    assert "agent" in node_names
```

**Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/test_agent.py -v`
Expected: FAIL — `ImportError`

**Step 3: 구현**

```python
# src/gp_claw/agent.py
from typing import Annotated, Any

from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
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
```

**Step 4: 테스트 실행 — 성공 확인**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/test_agent.py -v`
Expected: 3 PASSED

**Step 5: Commit**

```bash
git add src/gp_claw/agent.py tests/test_agent.py
git commit -m "feat: 기본 LangGraph 에이전트 (Phase 1 — 단순 대화)"
```

---

### Task 6: FastAPI WebSocket 서버

**Files:**
- Create: `src/gp_claw/server.py`
- Create: `tests/test_server.py`

**Step 1: 테스트 작성**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from gp_claw.server import create_app


def test_health_endpoint():
    """헬스체크 엔드포인트가 동작하는지 확인."""
    app = create_app()
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_websocket_connect():
    """WebSocket 연결이 수립되는지 확인."""
    app = create_app()
    client = TestClient(app)
    with client.websocket_connect("/ws/test-session") as ws:
        ws.send_json({"type": "ping"})
        data = ws.receive_json()
        assert data["type"] == "pong"
```

**Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/test_server.py -v`
Expected: FAIL — `ImportError`

**Step 3: 구현**

```python
# src/gp_claw/server.py
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """FastAPI 애플리케이션 생성."""
    app = FastAPI(title="GP Claw", version="0.1.0")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.websocket("/ws/{session_id}")
    async def websocket_endpoint(websocket: WebSocket, session_id: str):
        await websocket.accept()
        logger.info(f"WebSocket connected: session={session_id}")

        try:
            while True:
                data = await websocket.receive_json()

                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif data.get("type") == "user_message":
                    content = data.get("content", "")
                    # Phase 1: 에이전트 연결 전 에코 응답
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

**Step 4: 테스트 실행 — 성공 확인**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/test_server.py -v`
Expected: 2 PASSED

**Step 5: Commit**

```bash
git add src/gp_claw/server.py tests/test_server.py
git commit -m "feat: FastAPI WebSocket 서버 (헬스체크 + WS 연결)"
```

---

### Task 7: WebSocket + LangGraph 연동

**Files:**
- Modify: `src/gp_claw/server.py`
- Create: `tests/test_ws_agent.py`

**Step 1: 통합 테스트 작성**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from gp_claw.server import create_app


def test_websocket_user_message_gets_agent_response():
    """사용자 메시지를 보내면 에이전트 응답을 받는지 확인."""
    mock_llm = MagicMock()
    mock_response = AIMessage(content="안녕하세요! 도움이 필요하신가요?")
    mock_llm.ainvoke = AsyncMock(return_value=mock_response)

    app = create_app(llm=mock_llm)
    client = TestClient(app)

    with client.websocket_connect("/ws/test-session") as ws:
        ws.send_json({"type": "user_message", "content": "안녕"})
        data = ws.receive_json()
        assert data["type"] == "assistant_message"
        assert "안녕하세요" in data["content"]
```

**Step 2: 테스트 실행 — 실패 확인**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/test_ws_agent.py -v`
Expected: FAIL — `create_app()` 이 `llm` 파라미터를 받지 않음

**Step 3: server.py 수정 — LangGraph 연동**

```python
# src/gp_claw/server.py
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver

from gp_claw.agent import create_agent

logger = logging.getLogger(__name__)


def create_app(llm: ChatOpenAI | None = None) -> FastAPI:
    """FastAPI 애플리케이션 생성.

    Args:
        llm: LLM 인스턴스. None이면 에이전트 없이 에코 모드로 동작.
    """
    app = FastAPI(title="GP Claw", version="0.1.0")
    checkpointer = MemorySaver()
    agent = create_agent(llm, checkpointer=checkpointer) if llm else None

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
                        last_message = result["messages"][-1]
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

**Step 4: 테스트 실행 — 성공 확인**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/test_ws_agent.py tests/test_server.py -v`
Expected: ALL PASSED

**Step 5: Commit**

```bash
git add src/gp_claw/server.py tests/test_ws_agent.py
git commit -m "feat: WebSocket + LangGraph 에이전트 연동"
```

---

### Task 8: 엔트리포인트 및 수동 테스트

**Files:**
- Create: `src/gp_claw/__main__.py`

**Step 1: 엔트리포인트 작성**

```python
# src/gp_claw/__main__.py
import uvicorn

from gp_claw.config import Settings
from gp_claw.llm import create_llm
from gp_claw.server import create_app


def main():
    settings = Settings()

    llm = None
    if settings.runpod_api_key and settings.runpod_endpoint_id:
        llm = create_llm(settings)
        print(f"LLM connected: {settings.vllm_model_name}")
    else:
        print("No LLM configured — running in echo mode")

    app = create_app(llm=llm)
    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
```

**Step 2: 에코 모드로 서버 시작 테스트**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && timeout 5 python -m gp_claw || true`
Expected: `No LLM configured — running in echo mode` 출력 후 서버 시작

**Step 3: 전체 테스트 실행**

Run: `cd /Users/goldenplanet/jinsup_space/gp_claw && source .venv/bin/activate && python -m pytest tests/ -v`
Expected: ALL PASSED

**Step 4: Commit**

```bash
git add src/gp_claw/__main__.py
git commit -m "feat: 서버 엔트리포인트 추가 (에코 모드 + LLM 모드)"
```

---

## Phase 1 완료 체크리스트

- [ ] 프로젝트 구조 및 의존성 설정
- [ ] Settings 설정 및 테스트
- [ ] RunPod vLLM LLM 클라이언트
- [ ] 서브에이전트 보안 프롬프트 및 경로 검증
- [ ] 기본 LangGraph 에이전트 (단순 대화)
- [ ] FastAPI WebSocket 서버
- [ ] WebSocket + LangGraph 연동
- [ ] 엔트리포인트 및 수동 테스트

## Phase 2 예고

- Safe 도구 구현 (file_read, file_search, excel_read, pdf_read)
- Dangerous 도구 구현 (file_write, file_delete, gmail_send)
- Human-in-the-Loop 승인 워크플로우
- 7B/72B 라우터
- 메모리 시스템 (MEMORY.md + Daily Notes + 하이브리드 검색)
