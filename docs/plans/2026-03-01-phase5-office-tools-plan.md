# Phase 5: 사무용 도구 확장 + Markdown 렌더링

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 엑셀/CSV/PDF 등 사무용 파일 생성 도구를 추가하고, AI 응답을 Markdown으로 렌더링하여 프론트엔드에서 깔끔하게 표시.

**Architecture:** 기존 도구 패턴(`create_*_tools(workspace_root)`)을 따라 `office_file.py`에 사무용 도구를 추가. 프론트엔드에 `react-markdown` + `remark-gfm`으로 Markdown 렌더링.

**Tech Stack:** openpyxl (엑셀), reportlab (PDF), python-pptx (PPT), react-markdown, remark-gfm

---

## 사전 조사: 사무용 라이브러리 목록

| 라이브러리 | 용도 | 분류 |
|-----------|------|------|
| `openpyxl` | .xlsx 엑셀 파일 생성/수정 | Dangerous |
| `reportlab` | PDF 파일 생성 (텍스트, 표, 이미지) | Dangerous |
| `python-pptx` | .pptx 파워포인트 생성 | Dangerous |
| (내장 `csv`) | CSV 파일 생성 | Dangerous |

---

## Task 1: Python 의존성 설치

**Files:**
- Modify: `pyproject.toml`

**Step 1: pyproject.toml에 의존성 추가**

`dependencies` 섹션에 추가:
```toml
"openpyxl>=3.1",
"reportlab>=4.0",
"python-pptx>=1.0",
```

**Step 2: 설치**

```bash
pip install -e ".[dev]"
```

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "chore: 사무용 파일 라이브러리 의존성 추가"
```

---

## Task 2: 사무용 도구 구현 — `office_file.py`

**Files:**
- Create: `src/gp_claw/tools/office_file.py`
- Modify: `src/gp_claw/tools/__init__.py`

**Step 1: office_file.py 생성**

기존 `dangerous_file.py` 패턴을 따라 `create_office_tools(workspace_root)` 함수 구현:

```python
# 도구 목록:
# 1. excel_write(path, sheets) — 엑셀 파일 생성
#    sheets: [{"name": "Sheet1", "headers": [...], "rows": [[...], ...]}]
#
# 2. csv_write(path, headers, rows) — CSV 파일 생성
#
# 3. pdf_write(path, title, content) — PDF 파일 생성
#    content: 마크다운 텍스트 → PDF 변환
#
# 4. pptx_write(path, title, slides) — PPT 파일 생성
#    slides: [{"title": "...", "content": "..."}]
```

각 도구는:
- `workspace_root`로 경로 검증 (`security.validate_path`)
- 파일 생성 후 `{"path": ..., "size_bytes": ..., "action": "created"}` 반환
- 모두 Dangerous 분류 (파일 생성이므로 승인 필요)

**Step 2: `__init__.py` 수정**

```python
from gp_claw.tools.office_file import create_office_tools

def create_tool_registry(workspace_root: str) -> ToolRegistry:
    return ToolRegistry(
        safe_tools=create_safe_file_tools(workspace_root),
        dangerous_tools=(
            create_dangerous_file_tools(workspace_root)
            + create_office_tools(workspace_root)
        ),
    )
```

**Step 3: Commit**

```bash
git add src/gp_claw/tools/office_file.py src/gp_claw/tools/__init__.py
git commit -m "feat: 사무용 도구 추가 (excel, csv, pdf, pptx)"
```

---

## Task 3: 사무용 도구 테스트

**Files:**
- Create: `tests/test_office_tools.py`

**Step 1: 각 도구별 테스트 작성**

```python
# test_excel_write — .xlsx 생성 확인 + openpyxl로 내용 검증
# test_csv_write — .csv 생성 확인 + csv.reader로 내용 검증
# test_pdf_write — .pdf 생성 확인 + 파일 크기 > 0
# test_pptx_write — .pptx 생성 확인 + python-pptx로 슬라이드 수 검증
# test_office_tools_in_registry — 레지스트리에 등록 확인
# test_office_tools_path_validation — 워크스페이스 외부 경로 차단 확인
```

**Step 2: 테스트 실행**

```bash
python -m pytest tests/test_office_tools.py -v
```

**Step 3: Commit**

```bash
git add tests/test_office_tools.py
git commit -m "test: 사무용 도구 테스트"
```

---

## Task 4: 시스템 프롬프트에 사무용 도구 안내 추가

**Files:**
- Modify: `src/gp_claw/llm.py`

**Step 1: 시스템 프롬프트 보강**

`_build_tools_system_prompt` 함수의 프롬프트에 사무용 도구 사용 가이드 추가:
- 엑셀 요청 시 `excel_write` 도구 즉시 사용
- 보고서 요청 시 `pdf_write` 도구 사용
- 데이터 정리 시 `csv_write` 사용
- 발표자료 시 `pptx_write` 사용

**Step 2: Commit**

```bash
git add src/gp_claw/llm.py
git commit -m "feat: 시스템 프롬프트에 사무용 도구 가이드 추가"
```

---

## Task 5: 프론트엔드 — Markdown 렌더링

**Files:**
- Modify: `frontend/package.json` (의존성)
- Modify: `frontend/src/components/ChatMessage.tsx`

**Step 1: 의존성 설치**

```bash
cd frontend
npm install react-markdown remark-gfm
```

**Step 2: ChatMessage.tsx에 Markdown 렌더링 적용**

AI 응답(`assistant` 타입)에만 `ReactMarkdown` 적용:
- `remark-gfm` 플러그인으로 테이블, 취소선 등 지원
- 코드 블록 스타일링
- 사용자 메시지는 기존 plain text 유지

```tsx
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

// assistant 메시지일 때:
<ReactMarkdown remarkPlugins={[remarkGfm]}>
  {message.content}
</ReactMarkdown>
```

**Step 3: Markdown 스타일링**

Tailwind의 `prose` 클래스 또는 커스텀 스타일로 깔끔한 렌더링:
- 테이블 보더
- 코드 블록 배경색
- 리스트 스타일

**Step 4: 빌드 검증**

```bash
npm run build
```

**Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: AI 응답 Markdown 렌더링 (react-markdown + remark-gfm)"
```

---

## Task 6: 전체 빌드 검증 + E2E 테스트

**Step 1: Backend 테스트**

```bash
python -m pytest tests/ -q
```

**Step 2: Frontend 빌드**

```bash
cd frontend && npm run build
```

**Step 3: 수동 E2E 테스트**

1. "매출 데이터를 엑셀로 만들어줘" → 승인 카드 → 승인 → .xlsx 생성 확인
2. "회의록을 PDF로 만들어줘" → 승인 카드 → 승인 → .pdf 생성 확인
3. "파일 목록 보여줘" → Markdown 테이블로 표시 확인
4. 코드 블록 포함 응답 → 하이라이팅 확인

**Step 4: Commit**

```bash
git add -A
git commit -m "feat: Phase 5 사무용 도구 + Markdown 렌더링 완성"
```
