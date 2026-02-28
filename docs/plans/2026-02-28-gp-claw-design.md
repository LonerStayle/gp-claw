# GP Claw - 회사 내부 AI 사무 비서 설계 문서

## 프로젝트 개요

**목적**: 회사 내부에서 안전하게 사용할 수 있는 AI 사무 비서. 엑셀, 문서, 파일 관리, Gmail 등 사무 작업을 도와주되, 위험한 작업(파일 삭제/수정, 메일 발송)은 반드시 사용자 승인을 거침.

**핵심 동기**:
- 회사 데이터 유출 방지 (외부 API 대신 자체 호스팅 LLM)
- 비용 절감 (서버리스 GPU로 사용한 만큼만 과금)

**사용자**: 소규모 1-5명, 웹 UI로 상호작용

**벤치마크**: [OpenClaw](https://github.com/openclaw/openclaw) 아키텍처 참고 (특히 메모리 전략)

---

## 전체 아키텍처

```
┌──────────────┐    ┌─────────────────────────────────────┐    ┌──────────────────┐
│  React UI    │    │         FastAPI Server               │    │  RunPod          │
│  (채팅+승인)  │◀──▶│                                     │    │  Serverless      │
└──────────────┘    │  ┌─────────────────────────────┐    │    │                  │
    WebSocket       │  │ Complexity Router            │    │    │  A.X 4.0 7B  ◀───┤
    (로컬)          │  │  단순 → 7B / 복잡 → 72B       │    │    │  A.X 4.0 72B ◀───┤
                    │  └──────┬──────────────────────┘    │    └──────────────────┘
                    │         │                           │         vLLM (OpenAI API)
                    │  ┌──────▼──────────────────────┐    │
                    │  │ LangGraph Agent (메인 세션)    │    │
                    │  │  - 대화 히스토리               │    │
                    │  │  - 플래너 (복잡한 요청)         │    │
                    │  │  - Safe/Dangerous 라우팅      │    │
                    │  │  - Pre-Compaction Flush       │    │
                    │  └──────┬──────────────────────┘    │
                    │         │                           │
                    │  ┌──────▼──────────────────────┐    │
                    │  │ 서브에이전트 (도구 실행)        │    │
                    │  │  - 독립 컨텍스트               │    │
                    │  │  - 보안 프롬프트 적용           │    │
                    │  │  - 결과만 메인에 반환           │    │
                    │  └──────┬──────────────────────┘    │
                    │         │                           │
                    │  ┌──────▼──────────────────────┐    │
                    │  │ Memory Layer                 │    │
                    │  │  - MEMORY.md (장기)           │    │
                    │  │  - Daily Notes (단기)          │    │
                    │  │  - SQLite 하이브리드 검색       │    │
                    │  └─────────────────────────────┘    │
                    └─────────────────────────────────────┘
```

### 통신 흐름

```
[사용자 브라우저] ←── WebSocket (로컬) ──→ [FastAPI 서버] ←── HTTPS ──→ [RunPod vLLM]
      빠르고 간단                                외부지만 단순 API 호출
```

- 로컬 네트워크 내 WebSocket: SSL/방화벽 불필요, 지연시간 거의 0
- RunPod과의 통신: vLLM이 OpenAI-compatible API를 제공하므로 일반 HTTPS 호출

---

## 기술 스택

| 레이어 | 기술 | 비고 |
|--------|------|------|
| Frontend | React + TypeScript + Tailwind CSS | 채팅 UI + 승인 카드 |
| Backend | Python + FastAPI + LangGraph | 에이전트 로직 + WebSocket |
| LLM Serving | vLLM on RunPod Serverless | OpenAI-compatible API |
| Model | SK Telecom A.X 4.0 (7B + 72B 하이브리드) | 한국 비즈니스 최적화, 상업 이용 가능 |
| GPU | RunPod A6000 (48GB VRAM) | $1.22/hr, 서버리스 |
| 파일 처리 | openpyxl, pandas, python-docx, PyMuPDF, pyhwpx | 엑셀/워드/PDF/한글 |
| 이메일 | Google Gmail API (OAuth2) | 발송은 승인 필수 |
| 메모리 검색 | SQLite + sqlite-vec + FTS5 | 하이브리드 벡터+키워드 검색 |
| 체크포인터 | SQLite (langgraph-checkpoint-sqlite) | Human-in-the-loop 상태 저장 |

---

## LLM 선택: SK Telecom A.X 4.0 (7B + 72B 하이브리드)

### 선택 근거

- **Qwen2.5 기반** + 대규모 한국어 지속적 사전학습(CPT) 적용
- KMMLU 78.3, CLIcK 85.7 → GPT-4o(72.5, 80.2) 능가
- 한국어 처리 효율 GPT-4o 대비 33% 높음
- **상업 이용 완전 무료** (오픈소스 라이선스)
- 한국 비즈니스 환경에 최적화

### 라이선스 비교 (선택 과정)

| 모델 | 라이선스 | 상업 가능 | 결정 |
|------|---------|----------|------|
| EXAONE 4.0 32B | EXAONE License NC | ❌ (FriendliAI 계약 필요) | 제외 |
| EXAONE Deep 32B | EXAONE License NC | ❌ | 제외 |
| **A.X 4.0** | **오픈소스 (상업 가능)** | **✅** | **선택** |
| Qwen2.5-32B | Apache 2.0 | ✅ | 대안 |

### 7B + 72B 하이브리드 전략

```
User 요청
    │
    ▼
Complexity Router (규칙 기반 + 휴리스틱)
    │
    ├─ 단순 (7B Light) ──▶ 빠르고 저렴
    │   "이 파일 요약해줘"
    │   "오늘 날짜 알려줘"
    │   "엑셀 수식 알려줘"
    │
    └─ 복잡 (72B Standard) ──▶ 정확하고 깊음
        "Q4 매출 분석해서 보고서 써줘"
        "이 계약서 검토해줘"
        "김과장에게 보낼 메일 작성해줘"
```

**라우팅 기준:**
- 도구 호출 필요 여부, 출력 길이 예상, 다단계 추론 필요 여부
- 7B가 답변하다 품질 부족하면 → 72B로 자동 에스컬레이션

### GPU 비용

| 플랫폼 | GPU | VRAM | 시간당 비용 | 콜드스타트 |
|--------|-----|------|-----------|-----------|
| **RunPod Flex** | **A6000** | **48GB** | **~$1.22** | **FlashBoot <2초** |

- 72B (4-bit AWQ): ~36GB → A6000(48GB)에서 동작 가능
- 7B (4-bit AWQ): ~4GB → 여유롭게 동작

---

## 에이전트 구조: A+C 하이브리드 + 서브에이전트

기본은 **단일 에이전트**(빠른 응답), 복잡한 요청에만 **플래너** 거침.
도구 실행은 **서브에이전트로 분리**하여 컨텍스트 절약.

### 흐름도

```
User 요청
    │
    ▼
복잡도 판단 (LLM)
    │
    ├─ 단순 ──▶ Agent(LLM) ──▶ 도구 실행 (서브에이전트) ──▶ 응답
    │              │
    │         Safe/Dangerous 분기 (승인 로직)
    │
    └─ 복잡 ──▶ Planner(LLM) ──▶ 실행 계획 표시
                                      │
                                 [사용자 확인]
                                      │
                                 단계별 실행 (서브에이전트)
                                 (각 단계마다 Safe/Dangerous 분기)
```

### 메인 세션 vs 서브에이전트

```
┌─────────────────────────────────────────────┐
│           메인 세션 (72B or 7B)              │
│  - 사용자 대화 히스토리 유지                    │
│  - 의사결정, 플래닝                           │
│  - 컨텍스트 예산 관리                         │
│                                             │
│  "엑셀에서 Q4 매출 집계해서 메일로 보내줘"      │
│       │                                     │
│       ├─▶ [서브에이전트 1] 엑셀 읽기+집계      │
│       │   (독립 컨텍스트, 결과만 반환)          │
│       │   (보안 프롬프트 적용)                 │
│       │                                     │
│       ├─▶ [서브에이전트 2] 메일 초안 작성       │
│       │   (집계 결과만 입력, 히스토리 불필요)    │
│       │   (보안 프롬프트 적용)                 │
│       │                                     │
│       └─▶ 메인 세션: 결과 종합 + 사용자에게 승인 │
└─────────────────────────────────────────────┘
```

**원칙:**
- 메인 세션은 **대화 히스토리 + 의사결정**만 담당
- 도구 실행(엑셀 처리, 파일 읽기 등)은 서브에이전트로 분리 → **결과만 반환**
- 서브에이전트는 히스토리 불필요 → 컨텍스트 절약
- **서브에이전트에는 반드시 보안 프롬프트 적용**

### 서브에이전트 보안 프롬프트

모든 서브에이전트에 아래 보안 프롬프트가 주입됩니다:

```
[보안 규칙 - 반드시 준수]

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
   Dangerous 작업이 필요한 경우, 작업 내용을 메인 에이전트에 반환하여 승인을 요청하세요.
```

### LangGraph 코드 구조

```python
graph = StateGraph(AgentState)

# 노드
graph.add_node("complexity_check", check_complexity)  # 복잡도 판단
graph.add_node("planner", create_plan)                # 복잡한 요청용 플래너
graph.add_node("agent", call_llm)                     # 단일 에이전트 (LLM)
graph.add_node("subagent_safe", run_subagent_safe)    # 서브에이전트: Safe 도구
graph.add_node("approval", request_approval)          # 승인 요청 (WebSocket → UI)
graph.add_node("subagent_dangerous", run_subagent_dangerous)  # 승인 후 실행
graph.add_node("memory_flush", flush_to_memory)       # Pre-Compaction Flush

# 라우팅
graph.add_conditional_edges("complexity_check", route_complexity, {
    "simple": "agent",
    "complex": "planner",
})
graph.add_edge("planner", "agent")

graph.add_conditional_edges("agent", classify_tool, {
    "safe": "subagent_safe",
    "dangerous": "approval",
    "memory_flush": "memory_flush",
    "end": END,
})
graph.add_edge("subagent_safe", "agent")
graph.add_edge("memory_flush", "agent")
graph.add_conditional_edges("approval", check_user_decision, {
    "approved": "subagent_dangerous",
    "rejected": "agent",
})
graph.add_edge("subagent_dangerous", "agent")
```

---

## 도구 시스템

### 도구 분류 (안전 등급)

| 등급 | 승인 필요 | 서브에이전트 실행 |
|------|----------|----------------|
| **Safe** | 아니오 | 서브에이전트 직접 실행 |
| **Dangerous** ⚠️ | **예** | 메인 에이전트 승인 후 실행 |

### Safe 도구 상세

#### `file_read` — 파일 내용 읽기
| 항목 | 내용 |
|------|------|
| 설명 | 지정된 경로의 파일 내용을 텍스트로 반환 |
| 파라미터 | `path: str` (워크스페이스 내 상대/절대 경로), `encoding: str = "utf-8"` |
| 반환값 | `{"content": str, "size_bytes": int, "path": str}` |
| 보안 | `validate_path()`로 워크스페이스 외부 접근 차단 |

#### `file_search` — 파일 검색
| 항목 | 내용 |
|------|------|
| 설명 | 파일명/확장자/패턴으로 워크스페이스 내 파일 검색 |
| 파라미터 | `pattern: str` (glob 패턴, 예: `*.xlsx`), `directory: str = "."` |
| 반환값 | `{"files": [{"path": str, "name": str, "size_bytes": int, "modified": str}]}` |
| 보안 | 워크스페이스 내부만 검색 |

#### `file_list` — 디렉토리 목록
| 항목 | 내용 |
|------|------|
| 설명 | 지정 디렉토리의 파일/폴더 목록 반환 |
| 파라미터 | `directory: str = "."` |
| 반환값 | `{"entries": [{"name": str, "type": "file"|"dir", "size_bytes": int}]}` |
| 보안 | 워크스페이스 내부만 |

#### `excel_read` — 엑셀 읽기/분석
| 항목 | 내용 |
|------|------|
| 설명 | .xlsx/.csv 파일을 읽어 데이터 반환. 시트 선택, 범위 지정, 요약 통계 가능 |
| 파라미터 | `path: str`, `sheet: str = None` (None이면 첫 시트), `range: str = None` (예: `"A1:D10"`), `summary: bool = False` (True면 행/열 수, 컬럼명, 데이터타입 요약만 반환) |
| 반환값 | `{"data": list[list], "columns": list[str], "row_count": int, "sheet_name": str}` 또는 summary 모드면 `{"columns": [...], "dtypes": [...], "row_count": int, "sample": list[list]}` |
| 라이브러리 | openpyxl (xlsx), pandas (csv) |
| 보안 | 읽기 전용. 대용량 파일은 summary 모드로 반환하여 컨텍스트 절약 |

#### `pdf_read` — PDF 텍스트 추출
| 항목 | 내용 |
|------|------|
| 설명 | PDF 파일에서 텍스트 추출 |
| 파라미터 | `path: str`, `pages: str = None` (예: `"1-5"`, None이면 전체) |
| 반환값 | `{"text": str, "page_count": int, "extracted_pages": str}` |
| 라이브러리 | PyMuPDF (fitz) |

#### `hwp_read` — 한글 파일 읽기
| 항목 | 내용 |
|------|------|
| 설명 | .hwp/.hwpx 파일에서 텍스트 추출 |
| 파라미터 | `path: str` |
| 반환값 | `{"text": str, "page_count": int}` |
| 라이브러리 | pyhwpx |

#### `doc_read` — Word 문서 읽기
| 항목 | 내용 |
|------|------|
| 설명 | .docx 파일에서 텍스트 추출 |
| 파라미터 | `path: str` |
| 반환값 | `{"text": str, "paragraph_count": int}` |
| 라이브러리 | python-docx |

#### `gmail_read` — Gmail 읽기
| 항목 | 내용 |
|------|------|
| 설명 | Gmail 받은편지함에서 이메일 목록/내용 조회 |
| 파라미터 | `query: str = ""` (Gmail 검색 쿼리), `max_results: int = 10`, `message_id: str = None` (특정 메일 상세 조회) |
| 반환값 | 목록: `{"emails": [{"id": str, "from": str, "subject": str, "date": str, "snippet": str}]}`, 상세: `{"id": str, "from": str, "to": str, "subject": str, "body": str, "date": str, "attachments": list}` |
| 라이브러리 | Google Gmail API (OAuth2) |
| 보안 | 읽기 전용, OAuth2 scope: `gmail.readonly` |

#### `memory_search` — 메모리 검색
| 항목 | 내용 |
|------|------|
| 설명 | MEMORY.md 및 Daily Notes에서 관련 기억 검색 |
| 파라미터 | `query: str`, `max_results: int = 5` |
| 반환값 | `{"results": [{"text": str, "source": str, "score": float}]}` |
| 라이브러리 | sqlite-vec + SQLite FTS5 |

---

### Dangerous 도구 상세 ⚠️

> 모든 Dangerous 도구는 실행 전 사용자 승인 필요.
> 승인 카드에 도구명, 파라미터, 미리보기가 표시됨.

#### `file_write` ⚠️ — 파일 생성/덮어쓰기
| 항목 | 내용 |
|------|------|
| 설명 | 새 파일을 생성하거나 기존 파일을 덮어씀 |
| 파라미터 | `path: str`, `content: str`, `encoding: str = "utf-8"` |
| 반환값 | `{"path": str, "size_bytes": int, "action": "created"|"overwritten"}` |
| 승인 미리보기 | 파일 경로 + 내용 앞 500자 미리보기 |

#### `file_delete` ⚠️ — 파일 삭제
| 항목 | 내용 |
|------|------|
| 설명 | 지정된 파일을 삭제 |
| 파라미터 | `path: str` |
| 반환값 | `{"deleted": str, "size_bytes": int}` |
| 승인 미리보기 | 파일 경로 + 파일 크기 + 최종 수정 시간 |

#### `file_move` ⚠️ — 파일 이동/이름변경
| 항목 | 내용 |
|------|------|
| 설명 | 파일을 이동하거나 이름 변경 |
| 파라미터 | `source: str`, `destination: str` |
| 반환값 | `{"source": str, "destination": str}` |
| 승인 미리보기 | 원본 경로 → 대상 경로 |

#### `excel_write` ⚠️ — 엑셀 수정/생성
| 항목 | 내용 |
|------|------|
| 설명 | 엑셀 파일을 생성하거나 기존 파일의 셀/시트 수정 |
| 파라미터 | `path: str`, `data: list[list]` (2D 배열), `sheet: str = "Sheet1"`, `start_cell: str = "A1"`, `create_new: bool = False` |
| 반환값 | `{"path": str, "sheet": str, "rows_written": int, "action": "created"|"modified"}` |
| 승인 미리보기 | 파일 경로 + 수정될 시트/범위 + 데이터 앞 5행 미리보기 |
| 라이브러리 | openpyxl |

#### `doc_write` ⚠️ — Word 문서 작성
| 항목 | 내용 |
|------|------|
| 설명 | .docx 파일 생성 |
| 파라미터 | `path: str`, `content: str` (마크다운 형식 → docx 변환), `title: str = ""` |
| 반환값 | `{"path": str, "paragraph_count": int}` |
| 승인 미리보기 | 파일 경로 + 내용 앞 500자 |
| 라이브러리 | python-docx |

#### `gmail_send` ⚠️ — Gmail 발송
| 항목 | 내용 |
|------|------|
| 설명 | Gmail로 이메일 발송 |
| 파라미터 | `to: str`, `subject: str`, `body: str`, `cc: str = ""`, `attachments: list[str] = []` (파일 경로 목록) |
| 반환값 | `{"message_id": str, "to": str, "subject": str}` |
| 승인 미리보기 | 수신자, 제목, 본문 전체 미리보기, 첨부파일 목록 |
| 라이브러리 | Google Gmail API (OAuth2) |
| 보안 | OAuth2 scope: `gmail.send`, 승인 카드에서 수정 가능 |

#### `gmail_draft` ⚠️ — Gmail 임시저장
| 항목 | 내용 |
|------|------|
| 설명 | Gmail 임시저장함에 초안 저장 (발송하지 않음) |
| 파라미터 | `to: str`, `subject: str`, `body: str`, `cc: str = ""` |
| 반환값 | `{"draft_id": str, "to": str, "subject": str}` |
| 승인 미리보기 | 수신자, 제목, 본문 미리보기 |
| 라이브러리 | Google Gmail API (OAuth2) |

#### `memory_write` ⚠️ — 장기 메모리 저장
| 항목 | 내용 |
|------|------|
| 설명 | MEMORY.md에 영구 기억 저장/수정 |
| 파라미터 | `content: str`, `section: str = ""` (특정 섹션에 추가) |
| 반환값 | `{"path": str, "action": "appended"|"updated"}` |
| 승인 미리보기 | 저장될 내용 전체 |

---

### 도구 요약 테이블

| # | 도구명 | 등급 | 카테고리 | 라이브러리 |
|---|--------|------|---------|-----------|
| 1 | `file_read` | Safe | 파일시스템 | 내장 |
| 2 | `file_search` | Safe | 파일시스템 | 내장 (glob) |
| 3 | `file_list` | Safe | 파일시스템 | 내장 |
| 4 | `excel_read` | Safe | 파일 처리 | openpyxl, pandas |
| 5 | `pdf_read` | Safe | 파일 처리 | PyMuPDF |
| 6 | `hwp_read` | Safe | 파일 처리 | pyhwpx |
| 7 | `doc_read` | Safe | 파일 처리 | python-docx |
| 8 | `gmail_read` | Safe | 이메일 | Gmail API |
| 9 | `memory_search` | Safe | 메모리 | sqlite-vec, FTS5 |
| 10 | `file_write` | ⚠️ Dangerous | 파일시스템 | 내장 |
| 11 | `file_delete` | ⚠️ Dangerous | 파일시스템 | 내장 |
| 12 | `file_move` | ⚠️ Dangerous | 파일시스템 | 내장 (shutil) |
| 13 | `excel_write` | ⚠️ Dangerous | 파일 처리 | openpyxl |
| 14 | `doc_write` | ⚠️ Dangerous | 파일 처리 | python-docx |
| 15 | `gmail_send` | ⚠️ Dangerous | 이메일 | Gmail API |
| 16 | `gmail_draft` | ⚠️ Dangerous | 이메일 | Gmail API |
| 17 | `memory_write` | ⚠️ Dangerous | 메모리 | 내장 |

**총 17개 도구**: Safe 9개, Dangerous 8개

### 지원 파일 형식

| 파일 유형 | 라이브러리 | 용도 |
|-----------|-----------|------|
| `.xlsx` | openpyxl | 수식, 데이터 처리, 피벗 |
| `.csv` | pandas | 데이터 분석/변환 |
| `.docx` | python-docx | 보고서, 문서 작성 |
| `.pdf` | PyMuPDF / pdfplumber | PDF 읽기/텍스트 추출 |
| `.txt`, `.md` | 내장 | 일반 텍스트 |
| `.pptx` | python-pptx | 프레젠테이션 (필요시) |
| `.hwp/.hwpx` | pyhwpx | 한글 문서 |

---

## 승인 워크플로우 (Human-in-the-Loop)

### 단순 요청 승인 흐름

```
사용자: "김과장에게 회의 일정 메일 보내줘"
    │
    ▼
에이전트: Gmail 도구 호출 준비
    │
    ▼
⚠️ Dangerous 도구 감지 → 실행 중단
    │
    ▼
웹 UI에 승인 카드 표시:
  ┌─────────────────────────────┐
  │ Gmail 발송 요청              │
  │ To: kimkj@company.com       │
  │ 제목: 회의 일정 안내           │
  │ 내용: (미리보기)              │
  │                             │
  │    [승인]  [거부]  [수정]     │
  └─────────────────────────────┘
    │
    ▼
사용자 승인 → 실행 / 거부 → 취소 (에이전트에 거부 사유 전달)
```

### 복잡한 요청 승인 흐름

```
사용자: "엑셀에서 Q4 매출 집계해서 김과장에게 보내줘"
    │
    ▼
[복잡 판단] → Planner 실행
    │
    ▼
실행 계획 카드:
  ┌─────────────────────────────┐
  │ 실행 계획                    │
  │ 1. 매출_2025.xlsx 읽기       │
  │ 2. Q4 데이터 집계            │
  │ 3. 메일 초안 작성            │
  │ 4. ⚠️ Gmail 발송 (승인 필요) │
  │                             │
  │    [진행]  [취소]  [수정]     │
  └─────────────────────────────┘
    │
    ▼
단계별 실행 (4단계에서 다시 개별 승인)
```

### LangGraph interrupt 구현

```python
from langgraph.types import interrupt, Command

def request_approval(state):
    """Dangerous 도구 실행 전 사용자 승인 요청"""
    tool_call = state["pending_tool_call"]
    # interrupt()로 실행 중단, WebSocket으로 승인 카드 전송
    decision = interrupt({
        "type": "approval_request",
        "tool": tool_call["name"],
        "params": tool_call["args"],
        "preview": generate_preview(tool_call),
    })
    return {"user_decision": decision}

# 사용자 승인/거부 후 재개
# graph.stream(Command(resume={"decision": "approved"}), config)
```

---

## 컨텍스트 관리 및 KV 캐시 최적화

### KV 캐시 히트율 최적화

```
KV 캐시 구조 (앞쪽이 고정 → 캐시 히트):

┌──────────────────────────┐
│ System Prompt (고정)      │  ← 항상 캐시 히트
│ + MEMORY.md (느리게 변함)  │  ← 높은 캐시 히트
│ + 오늘의 Daily Notes      │  ← 세션 내 캐시 히트
├──────────────────────────┤
│ 대화 히스토리 (증가)       │  ← 뒤쪽만 새로 계산
│ + 최신 메시지              │  ← 새로 계산
└──────────────────────────┘
```

**전략:**
1. **Prefix Caching**: System Prompt + Memory가 앞에 고정 → vLLM의 prefix caching 활용
2. **서브에이전트 KV 분리**: 서브에이전트는 독립 요청 → 메인 KV 캐시 오염 없음
3. **도구 결과 압축**: 서브에이전트가 반환하는 결과를 요약/압축하여 메인 컨텍스트에 삽입

---

## 메모리 전략 (OpenClaw 참고)

### 설계 철학

> **"LLM 컨텍스트 = 캐시, 파일 = 원본"** (OS 가상 메모리 패턴)
>
> 모델은 파일에 기록된 것만 "기억"합니다. 나머지는 일시적입니다.

### 3단계 메모리 구조

| 계층 | 역할 | 위치 | 수명 |
|------|------|------|------|
| **Working Memory** | 현재 대화 컨텍스트 | LLM 컨텍스트 윈도우 | 세션 내 |
| **Daily Notes** | 오늘의 활동 기록 (append-only) | `memory/YYYY-MM-DD.md` | 하루 |
| **Long-term Memory** | 사용자 선호, 반복 패턴 (curated) | `MEMORY.md` | 영구 |

### 파일 구조

```
~/.gp_claw/
  workspace/
    MEMORY.md                     # 장기 기억 (사용자 선호, 결정사항)
    memory/
      2026-02-28.md              # 오늘의 기록
      2026-02-27.md              # 어제 기록
  index/
    memory.sqlite                 # 검색 인덱스 (임베딩 + FTS5)
```

### Pre-Compaction Flush (핵심 메커니즘)

```
컨텍스트가 가득 차기 전에:

[대화 진행 중...]
    │
    ▼
⚠️ 컨텍스트 80% 도달 감지
    │
    ▼
Silent Flush: "중요한 정보를 memory/2026-02-28.md에 저장해"
    │
    ▼
Compaction: 오래된 대화 요약/제거
    │
    ▼
[컨텍스트 여유 확보, 대화 계속]
```

- 컨텍스트 소진 전에 에이전트가 **스스로 중요 정보를 디스크에 저장**
- OS의 dirty-page writeback과 동일한 패턴

### 메모리 검색: 하이브리드 방식

```
사용자: "지난번에 김과장 메일 어떻게 썼었지?"
    │
    ▼
┌─ Vector Search (70%) ──▶ 의미적 유사도 (sqlite-vec)
│
└─ BM25 Keyword (30%) ──▶ 정확한 키워드 매칭 (SQLite FTS5)
    │
    ▼
관련 메모리 조각을 컨텍스트에 주입
```

### 세션 시작 시 메모리 로딩

```python
# 세션 시작 시 자동 로드
context = [
    system_prompt,                    # 고정 프롬프트
    read_file("MEMORY.md"),           # 장기 기억
    read_file("memory/2026-02-28.md"),  # 오늘 기록
    read_file("memory/2026-02-27.md"),  # 어제 기록
]
```

---

## 웹 UI 구성

### 주요 화면 요소

1. **채팅 인터페이스** — ChatGPT 스타일 대화창
2. **승인 요청 카드** — 도구명, 파라미터, 미리보기 + 승인/거부/수정 버튼
3. **실행 계획 카드** — 복잡한 요청 시 단계별 계획 표시
4. **파일 업로드/다운로드** — 드래그 앤 드롭으로 파일 첨부
5. **작업 히스토리** — 이전 대화 및 승인 이력

---

## 리서치 출처

- [SK Telecom A.X 4.0 Open Source Release - BusinessKorea](https://www.businesskorea.co.kr/news/articleView.html?idxno=246213)
- [SK Telecom A.X Press Release](https://www.sktelecom.com/en/press/press_detail.do?idx=1639)
- [Qwen2.5-32B-Instruct - HuggingFace](https://huggingface.co/Qwen/Qwen2.5-32B-Instruct)
- [OpenClaw Memory Docs](https://docs.openclaw.ai/concepts/memory)
- [OpenClaw Memory Architecture - Laurent Bindschaedler](https://binds.ch/blog/openclaw-systems-analysis/)
- [Meet South Korea's LLM Powerhouses - MarkTechPost](https://www.marktechpost.com/2025/08/21/meet-south-koreas-llm-powerhouses-hyperclova-ax-solar-pro-and-more/)
- [Korean LLMs Compared - Elice](https://elice.io/en/newsroom/llm-benchmark-korea-elice)
- [Top Serverless GPU Clouds 2026 - RunPod](https://www.runpod.io/articles/guides/top-serverless-gpu-clouds)
- [RunPod Serverless Pricing](https://docs.runpod.io/serverless/pricing)
- [RunPod vLLM Overview](https://docs.runpod.io/serverless/vllm/overview)
- [LangGraph Human-in-the-Loop](https://langchain-ai.github.io/langgraph/)
