# GP Claw Handoff Document

> 마지막 업데이트: 2026-03-01 (밤 세션)

## Goal

**GP Claw** — 회사 내부 AI 사무 비서. 파일/문서/Gmail 관리, 위험 작업은 승인 필수.
자체 호스팅 LLM(Mi:dm 2.0 Base 11.5B, KT) + RunPod Serverless GPU.

## Current Progress

| Phase | 상태 | 설명 |
|-------|------|------|
| 1. Foundation | ✅ | FastAPI + LangGraph + WebSocket |
| 2. Tool System + HITL | ✅ | 도구 레지스트리 + 승인 워크플로우 |
| 3. React Frontend | ✅ | 채팅 UI + 승인 카드 + WebSocket 연결 |
| 3.1 vLLM Tool Calling | ✅ | ToolParsingChatModel (`<tool_call>` 태그 파싱) |
| 4. 폴더 선택 기능 | ✅ | 프론트엔드에서 AI 작업 폴더 동적 변경 |
| 4.1 토큰 스트리밍 | ✅ | LangGraph astream_events + `<tool_call>` 버퍼링 |
| 4.2 시간 표시 | ✅ | 대화 메시지에 HH:MM 타임스탬프 |
| 4.3 프롬프트 강화 | ✅ | 한국어 few-shot 시스템 프롬프트 (temperature 0.3) |
| 5. 사무용 도구 + MD 렌더링 | ✅ | excel/csv/pdf/pptx 도구 + Markdown 렌더링 |
| 5.1 파일 열기 기능 | ✅ | file_open 도구 + FileCard UI + 열기 버튼 |
| 5.2 모델 교체 | ✅ | Mi:dm 2.0 Base (KT, 11.5B) |
| **6. Multi-Room Chat** | **✅** | **사이드바 대화방 CRUD + 방 전환 + 히스토리 복원** |
| **6.1 SQLite 영속성** | **🔜 다음 작업** | **인메모리 → SQLite 전환 (계획 완료, 구현 대기)** |

## 이번 세션에서 한 작업

### Multi-Room Chat 구현 완료 (커밋 안 됨)

ChatGPT/Claude 스타일의 왼쪽 사이드바 대화방 목록 기능을 구현함.

#### 신규 파일 (4개)
| 파일 | 목적 |
|------|------|
| `src/gp_claw/rooms.py` | Room 메타데이터 매니저 (인메모리 dict) |
| `tests/test_rooms.py` | Room CRUD + 메시지 히스토리 API 테스트 (12개) |
| `frontend/src/hooks/useRooms.ts` | Room CRUD + 활성 방 관리 훅 |
| `frontend/src/components/Sidebar.tsx` | 사이드바 UI (방 목록, 인라인 이름변경, 삭제 확인 다이얼로그) |

#### 수정 파일 (8개)
| 파일 | 변경 내용 |
|------|----------|
| `src/gp_claw/server.py` | REST 엔드포인트 6개 추가 (`/rooms` CRUD + `/rooms/{id}/messages`) + WS에서 room 자동생성/자동제목 |
| `frontend/src/hooks/useWebSocket.ts` | `roomId` 파라미터화, 히스토리 로드(`GET /rooms/{id}/messages`), `sessionStorage` 제거, `room_title_updated` 처리 |
| `frontend/src/types.ts` | `Room` 인터페이스 추가, `room_title_updated` WS 이벤트 타입 |
| `frontend/src/App.tsx` | 2열 레이아웃(Sidebar+Main), `useRooms` 통합, 사이드바 토글 버튼, `Cmd+Shift+O` 새 대화 단축키 |
| `frontend/vite.config.ts` | `/rooms` 프록시 추가 |
| `tests/test_ws_agent.py` | `room_title_updated` 이벤트 핸들링 추가 |
| `tests/test_ws_approval.py` | `room_title_updated` 이벤트 핸들링 추가 |
| `tests/test_agent_tools.py` | `room_title_updated` 이벤트 핸들링 추가 |

#### 검증 상태
- **73개 테스트 전부 통과** (`test_config.py` 1개 기존 실패 제외)
- 프론트엔드 TypeScript 타입 체크 통과 + 프로덕션 빌드 성공

### 현재 한계: 인메모리 저장
- Room 메타데이터(`RoomManager._rooms` dict)와 대화 히스토리(`MemorySaver`)가 모두 **인메모리**
- **서버 재시작 시 전부 사라짐** → SQLite 전환 필요

---

## Next Steps: SQLite 영속성 전환

### 구현 계획 (검증 완료)

상세 계획: `/Users/goldenplanet/.claude/plans/composed-shimmying-mango.md`

#### 핵심 설계
| 항목 | 결정 | 이유 |
|------|------|------|
| DB 파일 위치 | `~/.gp_claw/gp_claw.db` | 설정 가능, 프로젝트 간 충돌 없음 |
| Room 테이블 | `sqlite3` 직접 사용 | 단순 CRUD, 추가 의존성 불필요 |
| LangGraph 체크포인터 | `SqliteSaver` (동일 DB 파일) | `langgraph-checkpoint-sqlite>=2.0` 이미 의존성에 있음 |
| RoomManager API | 기존 인터페이스 유지 | server.py 호출부 변경 최소화 |
| 테스트 | `:memory:` SQLite 사용 | 테스트 격리 + 기존 패턴 호환 |

#### 5 단계 구현 순서

1. **`config.py`** — `db_path: Path = Path("~/.gp_claw/gp_claw.db")` 추가
2. **`rooms.py`** — `dict` → `sqlite3` 교체 (API 시그니처 동일 유지)
3. **`server.py`** — `MemorySaver()` → `SqliteSaver(conn)` + `RoomManager(db_path)`
   - **주의**: `SqliteSaver.from_conn_string()`은 context manager(Iterator)이므로, `sqlite3.connect()` + `SqliteSaver(conn)` + `setup()` 패턴 사용
4. **`__main__.py`** — DB 디렉토리 자동 생성 + `db_path` 전달
5. **테스트** — `create_app()` 기본값 `":memory:"` → 기존 73개 테스트 변경 불필요

#### 변경 파일
| 파일 | 변경 유형 |
|------|----------|
| `src/gp_claw/rooms.py` | 수정 (dict → SQLite) |
| `src/gp_claw/config.py` | 수정 (`db_path` 추가) |
| `src/gp_claw/server.py` | 수정 (`MemorySaver` → `SqliteSaver`) |
| `src/gp_claw/__main__.py` | 수정 (DB 디렉토리 생성 + `db_path` 전달) |
| `tests/test_rooms.py` | 확인 (변경 불필요할 가능성 높음) |

프론트엔드 변경 **없음**.

---

## What Worked

- LangGraph `MemorySaver`의 `thread_id` = Room ID 직접 매핑 → 변환 레이어 불필요
- `useWebSocket(roomId)` 파라미터화로 방 전환 시 WS 재연결 + 히스토리 로드 깔끔하게 동작
- `room_title_updated` WS 이벤트로 자동 제목 생성이 사이드바에 실시간 반영
- Radix Dialog로 삭제 확인 대화상자 기존 컴포넌트 재활용

## What Didn't Work / 주의사항

1. **`room_title_updated` 이벤트 추가 시 기존 테스트 5개 깨짐**: `assistant_done` 직전에 새 이벤트가 삽입되어 기존 WS 테스트들이 `room_title_updated`를 `assistant_done`으로 착각. 각 테스트에 수신 순서 추가하여 해결
2. **`SqliteSaver.from_conn_string()`은 context manager**: `yield`로 `SqliteSaver`를 반환하는 Iterator이므로 `create_app()` 같은 팩토리 함수에서 직접 사용 불가. `sqlite3.connect()` → `SqliteSaver(conn)` → `setup()` 패턴 사용해야 함
3. **RunPod GPU 호환성**: Ampere+ GPU 필요 (A40, A100, L40S). 구세대 GPU 시 CUDA Error 804
4. **VLLM_MODEL_NAME 대소문자**: RunPod이 모델명을 소문자로 등록하므로 `.env`도 소문자 필수
5. **test_config.py 1개 실패**: port 기본값 8002 반영 안 된 기존 버그 (기능에 영향 없음)

---

## 아키텍처

```
Frontend (Vite+React+TS:5173)  →  Vite proxy  →  Backend (FastAPI:8002)  →  RunPod vLLM
     ↕ WebSocket (streaming)                        ↕ LangGraph (astream_events)
  사이드바 + 채팅 UI + 승인 카드             safe/dangerous 도구 라우팅
  Markdown 렌더링 + 파일 카드              사무용 도구 (excel/csv/pdf/pptx/file_open)
  Room CRUD (useRooms hook)                Room REST API + 인메모리 RoomManager
```

## 핵심 파일

### Backend (`src/gp_claw/`)

| 파일 | 역할 |
|------|------|
| `__main__.py` | 엔트리포인트. Settings → LLM → Registry → App |
| `config.py` | Pydantic Settings. .env 연동 (temperature, max_tokens 등) |
| `server.py` | FastAPI + WebSocket + Room REST API. 스트리밍 + 승인 루프 + room 자동생성/자동제목 + 에러 복구 |
| `rooms.py` | **RoomManager** — Room CRUD (현재 인메모리 dict, SQLite 전환 예정) |
| `agent.py` | LangGraph 그래프. safe/dangerous 라우팅 + interrupt |
| `llm.py` | ToolParsingChatModel — 스트리밍 + tool_call 파싱. 한국어 few-shot 시스템 프롬프트 |
| `security.py` | 경로 검증. 워크스페이스 내부만 허용 |
| `tools/registry.py` | ToolRegistry. safe/dangerous 분류 |

### Frontend (`frontend/src/`)

| 파일 | 역할 |
|------|------|
| `App.tsx` | 메인 레이아웃 (Sidebar + Header + Chat + Input), 사이드바 토글, Cmd+Shift+O 단축키 |
| `hooks/useRooms.ts` | Room CRUD 훅 (fetch /rooms API, 활성 방 관리) |
| `hooks/useWebSocket.ts` | WS 연결 (`roomId` 파라미터), 방 전환 시 히스토리 로드, 스트리밍 수신 |
| `types.ts` | Room, Message, ToolCall, WsSend/WsReceive 타입 |
| `components/Sidebar.tsx` | 사이드바 (방 목록 + 새 대화 + 인라인 이름변경 + 삭제 확인) |
| `components/ChatContainer.tsx` | 메시지 리스트 + 자동 스크롤 |
| `components/ChatMessage.tsx` | user/assistant/error 버블 + Markdown 렌더링 |
| `components/ApprovalCard.tsx` | 승인/거부 카드 |

## WebSocket 프로토콜

```
Client → Server:  {"type": "user_message", "content": "..."}
                  {"type": "approval_response", "decision": "approved"|"rejected"}
                  {"type": "set_workspace", "path": "/Users/.../Desktop"}
                  {"type": "open_file", "path": "report.xlsx"}
                  {"type": "ping"}

Server → Client:  {"type": "assistant_chunk", "content": "토큰"}
                  {"type": "room_title_updated", "room_id": "...", "title": "..."}  ← 자동 제목
                  {"type": "assistant_done"}
                  {"type": "approval_request", "tool_calls": [{tool, args, preview}]}
                  {"type": "file_created", "path": "...", "filename": "...", "size_bytes": 0}
                  {"type": "workspace_changed", "path": "...", "display": "~/Desktop"}
                  {"type": "error", "content": "..."}
                  {"type": "pong"}
```

## Room REST API

```
GET    /rooms                    → 전체 방 목록 (최신순)
POST   /rooms                    → 새 방 생성 (body: {"title": "..."})
GET    /rooms/{room_id}          → 방 상세
PATCH  /rooms/{room_id}          → 제목 변경 (body: {"title": "..."})
DELETE /rooms/{room_id}          → 방 삭제 + 체크포인터 정리
GET    /rooms/{room_id}/messages → 대화 히스토리 (체크포인터에서 추출)
```

## 실행 방법

```bash
# Backend (터미널 1)
source .venv/bin/activate && python -m gp_claw  # → :8002

# Frontend (터미널 2)
cd frontend && npm run dev  # → :5173 (proxy → :8002)

# 테스트
source .venv/bin/activate && python -m pytest tests/ -q --ignore=tests/test_config.py
```

## 환경 변수 (.env)

```
RUNPOD_API_KEY=rpa_...
RUNPOD_ENDPOINT_ID=엔드포인트_ID
VLLM_MODEL_NAME=k-intelligence/midm-2.0-base-instruct  # 반드시 소문자
PORT=8002
WORKSPACE_ROOT=~/.gp_claw/workspace
LLM_MAX_TOKENS=8192
LLM_TEMPERATURE=0.3
```

## 알려진 이슈

1. **test_config.py 1개 실패** — port 기본값 8002 반영 안 된 기존 버그
2. **RunPod 콜드 스타트** — 첫 요청 시 빈 스트림 가능. 자동 1회 재시도 로직 있음
3. **인메모리 저장** — 서버 재시작 시 방 목록 + 대화 내역 초기화됨 ← **SQLite 전환으로 해결 예정**
