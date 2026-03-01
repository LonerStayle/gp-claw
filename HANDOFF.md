# GP Claw Handoff Document

> 마지막 업데이트: 2026-03-01

## Goal

**GP Claw** — 회사 내부 AI 사무 비서. 파일/문서/Gmail 관리, 위험 작업은 승인 필수.
자체 호스팅 LLM(skt/A.X-4.0-Light) + RunPod Serverless GPU.

## Current Progress

| Phase | 상태 | 설명 |
|-------|------|------|
| 1. Foundation | ✅ | FastAPI + LangGraph + WebSocket |
| 2. Tool System + HITL | ✅ | 도구 레지스트리 + 승인 워크플로우 (47 tests) |
| 3. React Frontend | ✅ | 채팅 UI + 승인 카드 + WebSocket 연결 |
| 3.1 vLLM Tool Calling | ✅ | ToolParsingChatModel (`<tool_call>` 태그 파싱) |
| **4. 폴더 선택 기능** | **❌** | **프론트엔드에서 AI 작업 폴더 선택 ← 다음 작업** |

## 아키텍처

```
Frontend (Vite+React+TS:5173)  →  Vite proxy  →  Backend (FastAPI:8002)  →  RunPod vLLM
     ↕ WebSocket                                    ↕ LangGraph
  채팅 UI + 승인 카드                          safe/dangerous 도구 라우팅
```

## 핵심 파일

### Backend (`src/gp_claw/`)

| 파일 | 역할 |
|------|------|
| `__main__.py` | 엔트리포인트. Settings → LLM → Registry → App |
| `config.py` | Pydantic Settings. 포트 8002, max_tokens 1024 |
| `server.py` | FastAPI + WebSocket. 승인 루프 + 에러 핸들링 |
| `agent.py` | LangGraph 그래프. safe/dangerous 라우팅 + interrupt |
| `llm.py` | **ToolParsingChatModel** — `<tool_call>` 태그 파싱 래퍼 |
| `security.py` | 경로 검증. 워크스페이스 내부만 허용 |
| `tools/registry.py` | ToolRegistry. safe/dangerous 분류 |
| `tools/safe_file.py` | file_read, file_search, file_list |
| `tools/dangerous_file.py` | file_write, file_delete, file_move (승인 필요) |

### Frontend (`frontend/src/`)

| 파일 | 역할 |
|------|------|
| `App.tsx` | 메인 레이아웃. 헤더 + 채팅 + 입력 |
| `hooks/useWebSocket.ts` | WS 연결, 자동 재연결, 승인 플로우 |
| `types.ts` | Message, ToolCall, WsSend/WsReceive 타입 |
| `components/ChatContainer.tsx` | 메시지 리스트 + 자동 스크롤 |
| `components/ChatMessage.tsx` | user/assistant/error 버블 |
| `components/ApprovalCard.tsx` | 승인/거부 카드 |
| `components/ChatInput.tsx` | 자동 리사이즈 + Enter 전송 |
| `components/ConnectionStatus.tsx` | 연결 상태 배지 |
| `components/ui/` | shadcn Button, Card, Badge |

## WebSocket 프로토콜

```
Client → Server:  {"type": "user_message", "content": "..."}
                  {"type": "approval_response", "decision": "approved"|"rejected"}
                  {"type": "ping"}

Server → Client:  {"type": "assistant_message", "content": "..."}
                  {"type": "approval_request", "tool_calls": [{tool, args, preview}]}
                  {"type": "error", "content": "..."}
                  {"type": "pong"}
```

## 알려진 이슈

1. **vLLM native tool calling 미지원** → ToolParsingChatModel로 해결 (시스템 프롬프트 + `<tool_call>` 파싱)
2. **워크스페이스 제한** — `~/.gp_claw/workspace` 안에서만 작동. Phase 4에서 폴더 선택으로 해결 예정
3. **test_config.py 1개 실패** — `~` 경로 확장 테스트 (기존 버그)

## 실행 방법

```bash
# Backend
source .venv/bin/activate && python -m gp_claw  # → :8002

# Frontend
cd frontend && npm run dev  # → :5173 (proxy → :8002)
```

## 환경 변수 (.env)

```
RUNPOD_API_KEY=rpa_...
RUNPOD_ENDPOINT_ID=fpyx62fxuj08vi
VLLM_MODEL_NAME=skt/A.X-4.0-Light
PORT=8002
WORKSPACE_ROOT=~/.gp_claw/workspace
```

## 다음 단계: Phase 4 — 폴더 선택 기능

프론트엔드에서 사용자가 AI 작업 폴더를 선택하는 기능.
상세 계획: `docs/plans/2026-03-01-folder-picker-design.md`

## 참고 문서

| 문서 | 경로 |
|------|------|
| 전체 설계 | `docs/plans/2026-02-28-gp-claw-design.md` |
| React 프론트엔드 설계 | `docs/plans/2026-03-01-react-frontend-design.md` |
| React 구현 플랜 | `docs/plans/2026-03-01-react-frontend-plan.md` |
| Phase 4 폴더 선택 설계 | `docs/plans/2026-03-01-folder-picker-design.md` |
