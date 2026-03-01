# GP Claw Handoff Document

> 마지막 업데이트: 2026-03-01 (저녁 세션)

## Goal

**GP Claw** — 회사 내부 AI 사무 비서. 파일/문서/Gmail 관리, 위험 작업은 승인 필수.
자체 호스팅 LLM(Mi:dm 2.0 Base 11.5B, KT) + RunPod Serverless GPU.

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
| 4.3 프롬프트 강화 | ✅ | 한국어 few-shot 시스템 프롬프트 (temperature 0.3) |
| 5. 사무용 도구 + MD 렌더링 | ✅ | excel/csv/pdf/pptx 도구 + Markdown 렌더링 (62 tests) |
| 5.1 파일 열기 기능 | ✅ | file_open 도구 + FileCard UI + 열기 버튼 |
| 5.2 모델 교체 | ✅ | skt/A.X-4.0-Light → Qwen2.5-14B → **Mi:dm 2.0 Base** (KT, 11.5B) |

## 이번 세션에서 한 작업

### 커밋되지 않은 변경사항 (중요!)

아래 변경사항이 모두 **스테이징 안 된 상태**로 남아있습니다.

#### 1. Thinking 태그 스트리밍 기능 제거 (이전 세션)
- `server.py`: `<think>`/`</think>` 파싱 로직 전체 삭제, `_find_partial_match` 헬퍼 삭제
- `types.ts`: `ThinkingMessage` 타입, thinking 관련 `WsReceive` 이벤트 삭제
- `useWebSocket.ts`: `thinking_start/chunk/done` 핸들러 삭제
- `ChatContainer.tsx`: `ThinkingBlock` import 및 렌더링 제거
- `ThinkingBlock.tsx`: 파일 자체 삭제

#### 2. Mi:dm 2.0 모델 교체 (이전 세션)
- `HANDOFF.md`, `README.md`: Qwen3-8B → Mi:dm 2.0 Base 반영
- `llm.py`: 한국어 강제 시스템 프롬프트 강화 (`<think>`도 한국어, 다른 언어 금지)

#### 3. 스트리밍 에러 복구 로직 (이전 세션)
- `server.py`: `_recover_thread()` 함수 추가 — 에러 시 오염된 체크포인트 정리 후 정상 메시지 복원

#### 4. `</tool_call>` 닫는 태그 누락 수정 (이번 세션) ★
- **문제**: Mi:dm 2.0이 `<tool_call>{...}` 만 출력하고 `</tool_call>` 닫는 태그를 안 붙임
- **`llm.py` `_parse_tool_calls()`**: 닫는 태그 없는 경우에도 fallback 정규식으로 파싱
- **`server.py` fallback**: `<tool_call>` 태그가 프론트엔드에 raw 노출되지 않도록 필터링

#### 5. 승인 루프 ping 간섭 수정 (이번 세션) ★
- **문제**: 프론트엔드 30초 ping이 승인 대기 중 `receive_json()`에 먼저 도착 → 자동 거부 처리
- **`server.py` 승인 루프**: ping을 내부에서 처리하는 while 루프 추가

### 검증 상태
- 61개 테스트 통과 (test_config.py 1개 기존 실패 제외)
- `_parse_tool_calls` 4가지 케이스 검증 완료 (닫는 태그 있음/없음, 텍스트 포함, 줄바꿈 포함)
- **실제 Mi:dm 2.0 연동 테스트는 아직 미완료** — 사용자가 서버 재시작 후 테스트 필요

## What Worked

- Mi:dm 2.0 Base가 RunPod에서 정상 기동됨 (GPU 호환성 문제 해결 후)
- 한국어로 응답하고 `<tool_call>` 형식으로 도구 호출 시도함
- `.env`의 `VLLM_MODEL_NAME`을 소문자(`k-intelligence/midm-2.0-base-instruct`)로 변경하니 모델 인식 성공

## What Didn't Work / 주의사항

1. **RunPod GPU 호환성**: vLLM v0.15.1 Docker 이미지는 Ampere 이상 GPU 필요. 구세대 GPU 배정 시 `Error 804: forward compatibility` 발생. 엔드포인트 GPU 타입을 A40/A100/L40S로 지정해야 함
2. **VLLM_MODEL_NAME 대소문자**: RunPod이 모델명을 소문자로 등록하므로 `.env`도 소문자 필수 (`K-intelligence/...` → `k-intelligence/...`)
3. **`NUM_GPU_BLOCKS_OVERRIDE=0`**: 기본값이 0이면 vLLM 에러. 환경변수 자체를 삭제해야 함
4. **Mi:dm 2.0 닫는 태그 누락**: 네이티브 chat template에는 `</tool_call>` 형식이 정의돼 있지만, 커스텀 시스템 프롬프트 사용 시 닫는 태그를 빠뜨리는 경향. fallback 파서로 대응 중
5. **Mi:dm 2.0 네이티브 tool calling**: chat template에 tool calling 지원이 내장되어 있음 (`tools` 파라미터 전달 시 활성화). 현재는 `ToolParsingChatModel`이 `tools`를 API에 안 보내고 시스템 프롬프트로 주입하는 방식

## 아키텍처

```
Frontend (Vite+React+TS:5173)  →  Vite proxy  →  Backend (FastAPI:8002)  →  RunPod vLLM
     ↕ WebSocket (streaming)                        ↕ LangGraph (astream_events)
  채팅 UI + 승인 카드 + 폴더 선택            safe/dangerous 도구 라우팅
  Markdown 렌더링 + 파일 카드              사무용 도구 (excel/csv/pdf/pptx/file_open)
```

## 핵심 파일

### Backend (`src/gp_claw/`)

| 파일 | 역할 |
|------|------|
| `__main__.py` | 엔트리포인트. Settings → LLM → Registry → App |
| `config.py` | Pydantic Settings. .env 연동 (temperature, max_tokens 등) |
| `server.py` | FastAPI + WebSocket. **스트리밍 응답** + 승인 루프(ping 처리) + 세션별 workspace + open_file + file_created 알림 + **에러 복구(_recover_thread)** |
| `agent.py` | LangGraph 그래프. safe/dangerous 라우팅 + interrupt |
| `llm.py` | **ToolParsingChatModel** — `_astream` 오버라이드로 스트리밍 + tool_call 파싱(닫는 태그 없어도 동작). 한국어 few-shot 시스템 프롬프트 |
| `security.py` | 경로 검증. 워크스페이스 내부만 허용 |
| `tools/registry.py` | ToolRegistry. safe/dangerous 분류 |
| `tools/safe_file.py` | file_read, file_search, file_list |
| `tools/dangerous_file.py` | file_write, file_delete, file_move (승인 필요) |
| `tools/office_file.py` | excel_write, csv_write, pdf_write, pptx_write, **file_open** (승인 필요) |

### Frontend (`frontend/src/`)

| 파일 | 역할 |
|------|------|
| `App.tsx` | 메인 레이아웃. 헤더 + 폴더 선택 + 채팅 + 입력 |
| `hooks/useWebSocket.ts` | WS 연결, 스트리밍 청크 수신, 승인 플로우, workspace 관리, **openFile + file_created 핸들러** |
| `types.ts` | Message(+timestamp+FileCardMessage), ToolCall, WsSend/WsReceive 타입 |
| `components/ChatContainer.tsx` | 메시지 리스트 + 자동 스크롤 + **FileCard 렌더링** |
| `components/ChatMessage.tsx` | user/assistant/error 버블 + **Markdown 렌더링** + 시간 표시 |
| `components/FileCard.tsx` | **파일 카드 (아이콘 + 파일명 + 크기 + 열기 버튼)** |
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
                  {"type": "open_file", "path": "report.xlsx"}
                  {"type": "ping"}

Server → Client:  {"type": "assistant_chunk", "content": "토큰"}     ← 스트리밍
                  {"type": "assistant_done"}                          ← 스트리밍 완료
                  {"type": "approval_request", "tool_calls": [{tool, args, preview}]}
                  {"type": "file_created", "path": "...", "filename": "...", "size_bytes": 0}
                  {"type": "file_opened", "path": "...", "filename": "..."}
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
  → ★ 닫는 태그(</tool_call>) 없어도 파싱 가능 (Mi:dm 2.0 대응)

server.py._stream_agent_response()
  → agent.astream_events()로 on_chat_model_stream 이벤트 수신
  → 일반 텍스트 → assistant_chunk로 WebSocket 전송
  → <tool_call> 감지 → 버퍼링 (프론트엔드에 안 보냄)
  → 스트리밍 미지원 agent → fallback (tool_call 태그 필터링 후 전송)
  → 도구 실행 후 file_created 알림 전송 (최근 턴 메시지만 스캔)
  → ★ 승인 대기 중 ping 메시지 내부 처리
```

**주의:** `astream_events`는 `_astream`을 호출합니다 (`_agenerate` 아님). 새 모델 래퍼 작성 시 `_astream`도 반드시 오버라이드해야 합니다.

## Next Steps (우선순위 순)

1. **실제 연동 테스트** — 서버 재시작 후 Mi:dm 2.0으로 도구 호출(file_list, excel_write 등) 정상 동작 확인
2. **커밋** — 이번 세션 변경사항 커밋 (thinking 제거 + Mi:dm 교체 + tool_call 파서 수정 + 승인 루프 수정)
3. **Mi:dm 2.0 네이티브 tool calling 전환 검토** — chat template에 내장된 tool calling 활용 시 `ToolParsingChatModel` 제거 가능. vLLM `--tool-call-parser` 옵션 사용
4. **test_config.py 수정** — port 기본값 8002 반영 (사소한 테스트 버그)

## 알려진 이슈

1. **test_config.py 1개 실패** — port 기본값 테스트 (기존 버그, 기능에 영향 없음)
2. **RunPod 콜드 스타트** — 첫 요청 시 빈 스트림 가능. 자동 1회 재시도 로직 추가됨
3. **VLLM_MODEL_NAME 대소문자** — RunPod이 모델명을 소문자로 등록하므로 `.env`도 소문자 필수
4. **RunPod GPU 호환성** — Ampere+ GPU 필요 (A40, A100, L40S). 구세대 GPU 시 CUDA Error 804
5. **NUM_GPU_BLOCKS_OVERRIDE** — 환경변수 자체를 삭제해야 함 (0으로 설정하면 에러)

## Mi:dm 2.0 Chat Template (참고)

Mi:dm 2.0은 네이티브 tool calling을 지원합니다. `tools` 파라미터가 전달되면 chat template이 자동으로:
- 도구 사용 규칙 (필수 인자 포함, tool_name 변경 금지 등) 주입
- `<tool_call></tool_call>` 형식 안내
- `tool_list`에 도구 정의 JSON 추가

현재는 `ToolParsingChatModel`이 이를 우회하고 시스템 프롬프트로 직접 주입하는 방식입니다.

## 실행 방법

```bash
# Backend (터미널 1)
source .venv/bin/activate && python -m gp_claw  # → :8002

# Frontend (터미널 2)
cd frontend && npm run dev  # → :5173 (proxy → :8002)
```

## 환경 변수 (.env)

```
# RunPod vLLM
RUNPOD_API_KEY=rpa_...
RUNPOD_ENDPOINT_ID=엔드포인트_ID
VLLM_MODEL_NAME=k-intelligence/midm-2.0-base-instruct  # ★ 반드시 소문자

# Server
PORT=8002
WORKSPACE_ROOT=~/.gp_claw/workspace

# LLM Parameters
LLM_MAX_TOKENS=8192
LLM_TEMPERATURE=0.3
```

## 사용자가 원하는 것 (대화에서 파악한 요구사항)

### 완료된 요구사항
- ✅ AI가 질문 없이 도구를 즉시 사용할 것 (한국어 few-shot 프롬프트)
- ✅ ChatGPT처럼 토큰 단위 실시간 스트리밍 응답
- ✅ 프론트엔드에서 작업 폴더 변경 가능
- ✅ 대화 메시지에 시간 표시
- ✅ 사무용 파일 생성 (엑셀, CSV, PDF, PPT)
- ✅ Markdown 렌더링 (react-markdown + remark-gfm)
- ✅ 파일 열기 (file_open 도구 + FileCard UI + 열기 버튼)
- ✅ 모델 교체 (skt/A.X-4.0-Light → Qwen2.5-14B → Mi:dm 2.0 Base)

### 장기적 방향 (추정)
- Gmail 연동 (설계 문서에 명시됨)
- 문서 요약/번역
- 워크플로우 자동화 (반복 업무)
- vLLM 네이티브 tool calling으로 전환 (ToolParsingChatModel 제거 가능)

## 참고 문서

| 문서 | 경로 |
|------|------|
| 전체 설계 | `docs/plans/2026-02-28-gp-claw-design.md` |
| React 프론트엔드 설계 | `docs/plans/2026-03-01-react-frontend-design.md` |
| Phase 4 폴더 선택 설계 | `docs/plans/2026-03-01-folder-picker-design.md` |
| 토큰 스트리밍 설계 | `docs/plans/2026-03-01-streaming-design.md` |
| Phase 5 계획 | `docs/plans/2026-03-01-phase5-office-tools-plan.md` |
| Phase 5.1 설계 | `docs/plans/2026-03-01-file-open-design.md` |
| Phase 5.1 계획 | `docs/plans/2026-03-01-file-open-plan.md` |
