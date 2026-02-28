# GP Claw - 회사 내부 AI 사무 비서 설계 문서

## 프로젝트 개요

**목적**: 회사 내부에서 안전하게 사용할 수 있는 AI 사무 비서. 엑셀, 문서, 파일 관리, Gmail 등 사무 작업을 도와주되, 위험한 작업(파일 삭제/수정, 메일 발송)은 반드시 사용자 승인을 거침.

**핵심 동기**:
- 회사 데이터 유출 방지 (외부 API 대신 자체 호스팅 LLM)
- 비용 절감 (서버리스 GPU로 사용한 만큼만 과금)

**사용자**: 소규모 1-5명, 웹 UI로 상호작용

**벤치마크**: [OpenClaw](https://github.com/openclaw/openclaw) 아키텍처 참고

---

## 아키텍처

```
┌─────────────────┐     ┌───────────────────────┐     ┌────────────────────────┐
│   React UI      │────▶│   FastAPI Server       │────▶│   RunPod Serverless    │
│   (채팅 + 승인)  │◀────│   (LangGraph Agent)    │◀────│   vLLM + EXAONE 32B    │
└─────────────────┘     └──────────┬────────────┘     └────────────────────────┘
     WebSocket (로컬)              │                       HTTPS (외부)
                           ┌───────┴────────┐
                           │     Tools      │
                           ├────────────────┤
                           │ 문서 작성/요약   │
                           │ 엑셀 처리       │
                           │ 파일 관리       │  ← 삭제/수정은 승인 필수
                           │ Gmail          │  ← 발송은 승인 필수
                           └────────────────┘
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
| Model | EXAONE 4.0 32B (AWQ 4-bit 양자화) | 한국어 사무 작업 최적 |
| GPU | RunPod A6000 (48GB VRAM) | $1.22/hr, 서버리스 |
| 파일 처리 | openpyxl, pandas, python-docx, PyMuPDF, pyhwpx | 엑셀/워드/PDF/한글 |
| 이메일 | Google Gmail API (OAuth2) | 발송은 승인 필수 |

---

## LLM 선택: EXAONE 4.0 32B

### 선택 근거

- 한국 모델 중 #1 (Intelligence Index 기준 오픈웨이트 4위, 세계 11위)
- 기업 문서/차트 해석 벤치마크(Chart QA) 세계 최고 수준
- LG AI Research 개발, 오픈웨이트 라이선스
- 4-bit 양자화(AWQ) 시 ~18GB VRAM → A6000 (48GB)에서 여유롭게 동작

### GPU 비용 비교 (선택 과정)

| 플랫폼 | GPU | VRAM | 시간당 비용 | 콜드스타트 |
|--------|-----|------|-----------|-----------|
| GCP Cloud Run | L4 | 24GB | ~$0.87 | 10-60초 |
| RunPod Flex | L4 | 24GB | ~$0.68 | FlashBoot <2초 |
| **RunPod Flex** | **A6000** | **48GB** | **~$1.22** | **FlashBoot <2초** |
| RunPod Flex | A100 | 80GB | ~$2.74 | FlashBoot <2초 |

**결정**: RunPod A6000 — 32B 4-bit에 충분한 여유(48GB), A100의 절반 가격, 빠른 콜드스타트

---

## 에이전트 구조: A+C 하이브리드

기본은 **단일 에이전트**(빠른 응답), 복잡한 요청에만 **플래너** 거침.

### 흐름도

```
User 요청
    │
    ▼
복잡도 판단 (LLM)
    │
    ├─ 단순 ──▶ Agent(LLM) ──▶ 도구 실행 ──▶ 응답
    │              │
    │         Safe/Dangerous 분기 (승인 로직)
    │
    └─ 복잡 ──▶ Planner(LLM) ──▶ 실행 계획 표시
                                      │
                                 [사용자 확인]
                                      │
                                 단계별 실행
                                 (각 단계마다 Safe/Dangerous 분기)
```

### 예시

- "이 파일 요약해줘" → **단순** → 바로 실행
- "엑셀에서 Q4 매출 집계해서 김과장에게 메일로 보내줘" → **복잡** → 계획: (1)엑셀 읽기 (2)집계 (3)메일 초안 (4)발송(승인) → 확인 후 실행

### LangGraph 코드 구조

```python
graph = StateGraph(AgentState)

# 노드
graph.add_node("complexity_check", check_complexity)  # 복잡도 판단
graph.add_node("planner", create_plan)                # 복잡한 요청용 플래너
graph.add_node("agent", call_llm)                     # 단일 에이전트 (LLM)
graph.add_node("safe_tools", run_safe)                # Safe 도구 즉시 실행
graph.add_node("approval", request_approval)          # 승인 요청 (WebSocket → UI)
graph.add_node("dangerous_tools", run_dangerous)      # 승인 후 실행

# 라우팅
graph.add_conditional_edges("complexity_check", route_complexity, {
    "simple": "agent",
    "complex": "planner",
})
graph.add_edge("planner", "agent")  # 계획 승인 후 단계별 실행

graph.add_conditional_edges("agent", classify_tool, {
    "safe": "safe_tools",
    "dangerous": "approval",
    "end": END,
})
graph.add_edge("safe_tools", "agent")
graph.add_conditional_edges("approval", check_user_decision, {
    "approved": "dangerous_tools",
    "rejected": "agent",
})
graph.add_edge("dangerous_tools", "agent")
```

---

## 도구 시스템

### 도구 분류 (안전 등급)

| 등급 | 도구 | 승인 필요 |
|------|------|----------|
| **Safe** | 문서 작성/요약, 엑셀 수식 생성, 파일 읽기/검색/목록, PDF 읽기, 한글 파일 읽기 | 아니오 |
| **Dangerous** | 파일 삭제/수정/이동/이름변경, 새 파일 생성, Gmail 발송 | **예** |

### 파일 접근 도구

```
파일 접근 도구 (파일시스템)         파일 처리 도구 (변환/편집)
├── file_search: 파일 검색         ├── excel_read: 엑셀 읽기/분석
├── file_read: 파일 내용 읽기       ├── excel_write: 엑셀 수정/생성  ⚠️
├── file_list: 디렉토리 목록        ├── doc_write: 문서 작성         ⚠️
├── file_move: 이동/이름변경  ⚠️    ├── pdf_read: PDF 텍스트 추출
├── file_delete: 삭제         ⚠️    └── hwp_read: 한글 파일 읽기
└── file_write: 새 파일 생성  ⚠️
```

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
  │ ✉️ Gmail 발송 요청            │
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
  │ 📋 실행 계획                  │
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
# Dangerous 도구는 interrupt_before로 실행 전 중단
graph.add_node("dangerous_tools", run_dangerous)

# LangGraph의 human-in-the-loop 패턴
config = {"configurable": {"thread_id": session_id}}
# interrupt 시 WebSocket으로 승인 요청 전송
# 사용자 응답 수신 후 graph.stream() 재개
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

- [Meet South Korea's LLM Powerhouses - MarkTechPost](https://www.marktechpost.com/2025/08/21/meet-south-koreas-llm-powerhouses-hyperclova-ax-solar-pro-and-more/)
- [Korea's AI challengers take on ChatGPT - The Korea Herald](https://www.koreaherald.com/article/10566046)
- [Best Open Source LLM For Korean 2026 - SiliconFlow](https://www.siliconflow.com/articles/en/best-open-source-llm-for-korean)
- [Korean LLMs Compared - Elice](https://elice.io/en/newsroom/llm-benchmark-korea-elice)
- [Top Serverless GPU Clouds 2026 - RunPod](https://www.runpod.io/articles/guides/top-serverless-gpu-clouds)
- [RunPod Serverless Pricing](https://docs.runpod.io/serverless/pricing)
- [RunPod vs GCP - RunPod](https://www.runpod.io/articles/comparison/runpod-vs-google-cloud-platform-inference)
