# GP Claw 핸드오프 문서

> 다음 세션에서 이 문서를 읽고 컨텍스트를 빠르게 파악한 후 작업을 이어가세요.

## Goal

**GP Claw** — 회사 내부 AI 사무 비서 시스템 구축.
엑셀/문서/파일/Gmail 등 사무 작업을 도와주며, 위험한 작업은 사용자 승인 필수.
자체 호스팅 LLM(SK Telecom A.X 4.0)으로 데이터 유출 방지.
**RunPod Serverless GPU**에 vLLM으로 모델 서빙 예정.

## Current Progress

### Phase 1: Foundation ✅ 완료

8개 태스크 완료, 16 tests.

| 모듈 | 파일 | 설명 |
|------|------|------|
| 프로젝트 설정 | `pyproject.toml`, `.env.example` | uv + Python 3.11, FastAPI/LangGraph/langchain-openai 의존성 |
| Settings | `src/gp_claw/config.py` | RunPod vLLM 설정, 서버 설정, pydantic-settings |
| LLM 클라이언트 | `src/gp_claw/llm.py` | RunPod vLLM 엔드포인트용 ChatOpenAI 래퍼 |
| 보안 모듈 | `src/gp_claw/security.py` | 서브에이전트 보안 프롬프트 + 경로 검증(validate_path) |
| LangGraph 에이전트 | `src/gp_claw/agent.py` | AgentState, create_agent |
| WebSocket 서버 | `src/gp_claw/server.py` | FastAPI + WebSocket, 에코/LLM 모드 |
| 엔트리포인트 | `src/gp_claw/__main__.py` | `python -m gp_claw`로 서버 시작 |

### Phase 2: Tool System + HITL ✅ 완료

8개 태스크 완료, 31 tests 추가 (총 47 tests).

| 모듈 | 파일 | 설명 |
|------|------|------|
| ToolRegistry | `src/gp_claw/tools/registry.py` | Safe/Dangerous 도구 분류, classify() |
| Safe 파일 도구 | `src/gp_claw/tools/safe_file.py` | `file_read`, `file_search`, `file_list` — 바로 실행 |
| Dangerous 파일 도구 | `src/gp_claw/tools/dangerous_file.py` | `file_write`, `file_delete`, `file_move` — 승인 필요 |
| 도구 팩토리 | `src/gp_claw/tools/__init__.py` | `create_tool_registry(workspace_root)` |
| Agent 그래프 | `src/gp_claw/agent.py` | safe → ToolNode 직접 실행, dangerous → interrupt() → 승인/거부 |
| WebSocket 서버 | `src/gp_claw/server.py` | 승인 카드 전송 + approval_response 처리 |

**그래프 토폴로지:**
```
START -> agent -> route_tool_call
    -> "end" -> END
    -> "safe" -> safe_tools -> agent
    -> "dangerous" -> approval -> route_approval
        -> "approved" -> dangerous_tools -> agent
        -> "rejected" -> handle_rejection -> agent
```

### 현재 상태: 서버 코드는 완성, LLM 연결은 미설정

서버는 `python -m gp_claw`로 실행 가능 (에코 모드).
**RunPod Serverless에 vLLM 엔드포인트가 아직 세팅되지 않음.**
`.env` 파일에 `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID` 설정 필요.

## 아직 안 된 것

- [x] Phase 1 구현 ✅
- [x] Phase 2 구현 ✅
- [ ] **RunPod Serverless GPU 세팅** ← 다음 작업 (사용자가 RunPod 서버리스 처음)
- [ ] 문서 포맷 도구 (excel_read, pdf_read, hwp_read, doc_read, excel_write, doc_write)
- [ ] Gmail 도구 (gmail_read, gmail_send, gmail_draft) + Google OAuth2
- [ ] 메모리 시스템 (MEMORY.md + Daily Notes + 하이브리드 검색)
- [ ] 7B/72B 복잡도 라우터
- [ ] React 프론트엔드
- [ ] RunPod 배포

## What Worked

1. **uv로 Python 환경 관리** — macOS 시스템 Python이 3.9.6이라 `uv venv --python 3.11`로 해결
2. **Worktree 기반 개발** — `.worktrees/`에 격리 작업 후 main으로 --no-ff 머지
3. **TDD 접근** — 테스트 먼저 → 구현 → 통과 → 커밋
4. **MemorySaver 체크포인터** — 인메모리로 테스트 통과
5. **Phase 2 plan-driven 개발** — 플랜 문서대로 8개 태스크를 3배치로 나눠 실행, 모두 한 번에 통과

## What Didn't Work

1. **macOS 경로 심볼릭 링크** — `/etc` → `/private/etc`. 해결: 워크스페이스 내부 검사 우선
2. **`timeout` 명령어** — macOS에 없음. import 검증으로 대체
3. **Phase 2 플랜의 create_tool_registry 순서** — Task 4에서 필요한데 Task 6에서 정의됨. 해결: Task 2에서 safe-only 버전 먼저 생성

## Next Steps

### 즉시: RunPod Serverless GPU 세팅

**사용자 상황:** RunPod 서버리스 경험 없음. 아래 내용을 안내해야 함:

1. **RunPod 계정 생성** — https://runpod.io
2. **Serverless Endpoint 생성**
   - vLLM Worker 사용
   - 모델: `SKTelecom/A.X-4.0-7B` (또는 적절한 양자화 버전)
   - GPU 선택: A5000 (24GB VRAM) 또는 A6000 (48GB)
   - Min/Max Workers 설정
3. **API Key 발급** — RunPod Settings에서 생성
4. **GP Claw .env 설정:**
   ```
   RUNPOD_API_KEY=<발급받은 키>
   RUNPOD_ENDPOINT_ID=<엔드포인트 ID>
   VLLM_MODEL_NAME=SKTelecom/A.X-4.0-7B
   ```
5. **연결 테스트** — `python -m gp_claw` 실행 후 WebSocket으로 대화 확인

**코드 쪽은 준비 완료:**
- `src/gp_claw/config.py` — `RUNPOD_API_KEY`, `RUNPOD_ENDPOINT_ID`, `VLLM_MODEL_NAME` 환경변수 지원
- `src/gp_claw/llm.py` — RunPod vLLM 엔드포인트를 ChatOpenAI 호환 클라이언트로 래핑
- OpenAI 호환 API: `https://{endpoint_id}-openai.runpod.ai/v1`

### 핵심 참고 문서

| 문서 | 경로 |
|------|------|
| 전체 설계 | `docs/plans/2026-02-28-gp-claw-design.md` |
| Phase 2 플랜 (완료) | `docs/plans/2026-02-28-gp-claw-phase2-plan.md` |
| Phase 1 플랜 (완료) | `docs/plans/2026-02-28-gp-claw-phase1-plan.md` |

### 주의사항

1. **EXAONE 사용 금지** — 비상업 라이선스. A.X 4.0만 사용
2. **서브에이전트에 보안 프롬프트 필수** — `security.py`의 `SUBAGENT_SECURITY_PROMPT`
3. **Dangerous 도구는 반드시 승인 흐름** — 직접 실행 불가
4. **uv 사용** — pip 대신 uv
5. **Python 3.11** — `uv venv --python 3.11 .venv && source .venv/bin/activate && uv pip install -e ".[dev]"`

## 실행 방법

```bash
# 에코 모드 (LLM 없이)
source .venv/bin/activate
python -m gp_claw

# LLM 모드 (.env 설정 후)
source .venv/bin/activate
python -m gp_claw
# → "LLM connected: SKTelecom/A.X-4.0-7B" 출력 확인

# 테스트
pytest -v  # 47 tests
```

## Git 상태

- 브랜치: `main`
- 최신 커밋: Phase 2 머지 완료
- Worktree: 정리됨
- 미추적 파일: `.DS_Store`, `HANDOFF.md`, Phase 2 플랜 문서
