# GP Claw Handoff Document

> 마지막 업데이트: 2026-03-01

## Goal

**GP Claw** — 회사 내부 AI 사무 비서. 파일/문서/Gmail 관리, 위험 작업은 승인 필수.
자체 호스팅 LLM(skt/A.X-4.0-Light) + RunPod Serverless GPU.

## Current Progress

| Phase | 상태 | 설명 |
|-------|------|------|
| 1. Foundation | ✅ | FastAPI + LangGraph + WebSocket |
| 2. Tool System + HITL | ✅ | 도구 레지스트리 + 승인 워크플로우 (45 tests) |
| 3. React Frontend | ✅ | 채팅 UI + 승인 카드 + WebSocket 연결 |
| 3.1 vLLM Tool Calling | ✅ | ToolParsingChatModel (`<tool_call>` 태그 파싱) |
| 4. 폴더 선택 기능 | ✅ | 프론트엔드에서 AI 작업 폴더 동적 변경 |
| 4.1 토큰 스트리밍 | ✅ | LangGraph astream_events + `<tool_call>` 버퍼링 |
| 4.2 시간 표시 | ✅ | 대화 메시지에 HH:MM 타임스탬프 |
| 4.3 프롬프트 강화 | ✅ | AI가 도구를 즉시 사용하도록 시스템 프롬프트 개선 |
| **5. 사무용 도구 + MD 렌더링** | **❌** | **엑셀/CSV/PDF/PPT 도구 + Markdown 렌더링 ← 다음 작업** |

## 아키텍처

```
Frontend (Vite+React+TS:5173)  →  Vite proxy  →  Backend (FastAPI:8002)  →  RunPod vLLM
     ↕ WebSocket (streaming)                        ↕ LangGraph (astream_events)
  채팅 UI + 승인 카드 + 폴더 선택            safe/dangerous 도구 라우팅
```

## 핵심 파일

### Backend (`src/gp_claw/`)

| 파일 | 역할 |
|------|------|
| `__main__.py` | 엔트리포인트. Settings → LLM → Registry → App |
| `config.py` | Pydantic Settings. 포트 8002, max_tokens 1024 |
| `server.py` | FastAPI + WebSocket. **스트리밍 응답** + 승인 루프 + 세션별 workspace |
| `agent.py` | LangGraph 그래프. safe/dangerous 라우팅 + interrupt |
| `llm.py` | **ToolParsingChatModel** — `_astream` 오버라이드로 스트리밍 + tool_call 파싱 |
| `security.py` | 경로 검증. 워크스페이스 내부만 허용 |
| `tools/registry.py` | ToolRegistry. safe/dangerous 분류 |
| `tools/safe_file.py` | file_read, file_search, file_list |
| `tools/dangerous_file.py` | file_write, file_delete, file_move (승인 필요) |

### Frontend (`frontend/src/`)

| 파일 | 역할 |
|------|------|
| `App.tsx` | 메인 레이아웃. 헤더 + 폴더 선택 + 채팅 + 입력 |
| `hooks/useWebSocket.ts` | WS 연결, 스트리밍 청크 수신, 승인 플로우, workspace 관리 |
| `types.ts` | Message(+timestamp), ToolCall, WsSend/WsReceive 타입 |
| `components/ChatContainer.tsx` | 메시지 리스트 + 자동 스크롤 |
| `components/ChatMessage.tsx` | user/assistant/error 버블 + **시간 표시** |
| `components/ApprovalCard.tsx` | 승인/거부 카드 |
| `components/ChatInput.tsx` | 자동 리사이즈 + Enter 전송 |
| `components/FolderPicker.tsx` | 폴더 선택 모달 (퀵 버튼 + 경로 입력) |
| `components/ConnectionStatus.tsx` | 연결 상태 배지 |
| `components/ui/` | shadcn Button, Card, Badge, Dialog |

## WebSocket 프로토콜

```
Client → Server:  {"type": "user_message", "content": "..."}
                  {"type": "approval_response", "decision": "approved"|"rejected"}
                  {"type": "set_workspace", "path": "/Users/.../Desktop"}
                  {"type": "ping"}

Server → Client:  {"type": "assistant_chunk", "content": "토큰"}     ← 스트리밍
                  {"type": "assistant_done"}                          ← 스트리밍 완료
                  {"type": "approval_request", "tool_calls": [{tool, args, preview}]}
                  {"type": "workspace_changed", "path": "...", "display": "~/Desktop"}
                  {"type": "workspace_error", "content": "..."}
                  {"type": "error", "content": "..."}
                  {"type": "pong"}
```

## 스트리밍 구조 (중요)

```
ToolParsingChatModel._astream()
  → 시스템 프롬프트(도구 정의) 주입
  → super()._astream()으로 토큰 스트리밍
  → 스트리밍 완료 후 <tool_call> 태그 파싱 → tool_call_chunks로 LangGraph 전달

server.py._stream_agent_response()
  → agent.astream_events()로 on_chat_model_stream 이벤트 수신
  → 일반 텍스트 → assistant_chunk로 WebSocket 전송
  → <tool_call> 감지 → 버퍼링 (프론트엔드에 안 보냄)
  → 스트리밍 미지원 agent → fallback으로 최종 메시지 전송
```

**주의:** `astream_events`는 `_astream`을 호출합니다 (`_agenerate` 아님). 새 모델 래퍼 작성 시 `_astream`도 반드시 오버라이드해야 합니다.

## 알려진 이슈

1. **test_config.py 2개 실패** — `~` 경로 확장 테스트 (기존 버그, 기능에 영향 없음)
2. **LLM 도구 호출 비결정성** — 같은 프롬프트에도 도구를 안 쓸 때가 있음. 시스템 프롬프트로 개선했지만 100%는 아님
3. **RunPod 콜드 스타트** — 첫 요청 시 500 에러 가능. 워커가 활성화되면 정상

## 실행 방법

```bash
# Backend (터미널 1)
source .venv/bin/activate && python -m gp_claw  # → :8002

# Frontend (터미널 2)
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

## 사용자가 원하는 것 (대화에서 파악한 요구사항)

### 완료된 요구사항
- ✅ AI가 질문 없이 도구를 즉시 사용할 것 (시스템 프롬프트 강화)
- ✅ ChatGPT처럼 토큰 단위 실시간 스트리밍 응답
- ✅ 프론트엔드에서 작업 폴더 변경 가능
- ✅ 대화 메시지에 시간 표시

### 다음 요구사항 (Phase 5)
- ❌ **사무용 파일 생성**: 엑셀(.xlsx), CSV, PDF, PPT 등 사무 문서를 AI가 직접 생성
- ❌ **Markdown 렌더링**: AI 응답을 Markdown 형식으로 이쁘게 표시 (테이블, 코드 블록 등)
- ❌ **OpenClaw 같은 경험**: 자연어로 "매출 엑셀 만들어줘"하면 바로 .xlsx 생성

### 장기적 방향 (추정)
- Gmail 연동 (설계 문서에 명시됨)
- 문서 요약/번역
- 워크플로우 자동화 (반복 업무)

## 다음 단계: Phase 5 — 사무용 도구 + Markdown 렌더링

상세 계획: `docs/plans/2026-03-01-phase5-office-tools-plan.md`

| Task | 내용 |
|------|------|
| 1 | Python 의존성 설치 (openpyxl, reportlab, python-pptx) |
| 2 | office_file.py — excel_write, csv_write, pdf_write, pptx_write 도구 |
| 3 | 도구 테스트 작성 |
| 4 | 시스템 프롬프트에 사무용 도구 가이드 추가 |
| 5 | react-markdown + remark-gfm으로 Markdown 렌더링 |
| 6 | 전체 빌드 검증 |

## 참고 문서

| 문서 | 경로 |
|------|------|
| 전체 설계 | `docs/plans/2026-02-28-gp-claw-design.md` |
| React 프론트엔드 설계 | `docs/plans/2026-03-01-react-frontend-design.md` |
| Phase 4 폴더 선택 설계 | `docs/plans/2026-03-01-folder-picker-design.md` |
| 토큰 스트리밍 설계 | `docs/plans/2026-03-01-streaming-design.md` |
| **Phase 5 계획** | `docs/plans/2026-03-01-phase5-office-tools-plan.md` |
