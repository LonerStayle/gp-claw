from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from gp_claw.server import create_app
from gp_claw.tools import create_tool_registry
from gp_claw.tools.registry import ToolRegistry


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.bind_tools = MagicMock(return_value=llm)
    return llm


def test_ws_dangerous_tool_sends_approval_request(workspace, mock_llm):
    """Dangerous 도구 호출 시 WebSocket으로 approval_request 전송."""
    mock_llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(
            content="",
            tool_calls=[{
                "name": "file_write",
                "args": {"path": "test.txt", "content": "hello"},
                "id": "call_1",
            }],
        ),
        AIMessage(content="파일을 작성했습니다."),
    ])

    registry = create_tool_registry(str(workspace))
    app = create_app(llm=mock_llm, registry=registry)
    client = TestClient(app)

    with client.websocket_connect("/ws/approval-ws-1") as ws:
        ws.send_json({"type": "user_message", "content": "test.txt에 hello 써줘"})

        # 승인 요청 수신
        data = ws.receive_json()
        assert data["type"] == "approval_request"
        assert data["tool_calls"][0]["tool"] == "file_write"

        # 승인
        ws.send_json({"type": "approval_response", "decision": "approved"})

        # 최종 응답
        data = ws.receive_json()
        assert data["type"] == "assistant_chunk"
        assert "작성" in data["content"]
        done = ws.receive_json()
        assert done["type"] == "assistant_done"

    # 파일이 실제로 생성되었는지 확인
    assert (workspace / "test.txt").read_text() == "hello"


def test_ws_dangerous_tool_rejection(workspace, mock_llm):
    """거부 시 도구 실행 안 되고 거부 메시지 전달."""
    mock_llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(
            content="",
            tool_calls=[{
                "name": "file_delete",
                "args": {"path": "important.txt"},
                "id": "call_1",
            }],
        ),
        AIMessage(content="알겠습니다. 삭제를 취소합니다."),
    ])

    (workspace / "important.txt").write_text("keep me")
    registry = create_tool_registry(str(workspace))
    app = create_app(llm=mock_llm, registry=registry)
    client = TestClient(app)

    with client.websocket_connect("/ws/approval-ws-2") as ws:
        ws.send_json({"type": "user_message", "content": "important.txt 삭제해줘"})

        data = ws.receive_json()
        assert data["type"] == "approval_request"

        ws.send_json({"type": "approval_response", "decision": "rejected"})

        data = ws.receive_json()
        assert data["type"] == "assistant_chunk"
        assert "취소" in data["content"]
        done = ws.receive_json()
        assert done["type"] == "assistant_done"

    # 파일이 삭제되지 않았는지 확인
    assert (workspace / "important.txt").exists()


def test_ws_safe_tool_no_approval_needed(workspace, mock_llm):
    """Safe 도구는 승인 없이 바로 실행."""
    (workspace / "doc.txt").write_text("내용입니다")

    mock_llm.ainvoke = AsyncMock(side_effect=[
        AIMessage(
            content="",
            tool_calls=[{
                "name": "file_read",
                "args": {"path": "doc.txt"},
                "id": "call_1",
            }],
        ),
        AIMessage(content="파일 내용: 내용입니다"),
    ])

    registry = create_tool_registry(str(workspace))
    app = create_app(llm=mock_llm, registry=registry)
    client = TestClient(app)

    with client.websocket_connect("/ws/approval-ws-3") as ws:
        ws.send_json({"type": "user_message", "content": "doc.txt 읽어줘"})

        # 승인 요청 없이 바로 응답
        data = ws.receive_json()
        assert data["type"] == "assistant_chunk"
        assert "내용입니다" in data["content"]
        done = ws.receive_json()
        assert done["type"] == "assistant_done"
