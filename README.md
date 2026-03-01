# GP Claw

회사 내부 AI 사무 비서. 파일 관리 + 사무용 문서 생성, 위험 작업은 사람 승인 필수.
자체 호스팅 LLM(Mi:dm 2.0 Base 11.5B) + RunPod Serverless GPU.

## 아키텍처

```
Frontend (Vite+React+TS:5173)  →  Vite proxy  →  Backend (FastAPI:8002)  →  RunPod vLLM
     ↕ WebSocket (streaming)                        ↕ LangGraph (astream_events)
  채팅 UI + 승인 카드 + 폴더 선택            safe/dangerous 도구 라우팅
  Markdown 렌더링 + 파일 카드              사무용 도구 (excel/csv/pdf/pptx)
```

---

## 1. RunPod Serverless 세팅

### 1-1. 서버리스 엔드포인트 생성

1. [RunPod](https://runpod.io) 가입
2. **Serverless** 탭 선택
3. 스크롤을 내려서 **vLLM** 카드 선택
4. **Deploy** 버튼 클릭
5. **MODEL NAME**에 `K-intelligence/Midm-2.0-Base-Instruct` 입력
6. 서버리스 생성 완료

### 1-2. GPU 설정

1. 생성된 엔드포인트의 **Manage** → **Edit Endpoint** 선택
2. **GPU Configuration**에서 사용할 GPU 선택
   - `Mi:dm 2.0 Base`는 **48GB** VRAM 권장 (A40, A6000 등)
   - 모델 ~23GB + KV cache 여유 필요

### 1-3. 환경 변수 설정

Edit Endpoint 화면에서 스크롤을 내리면 **Environment Variables** 란이 있습니다. 아래 값들을 추가하세요:

| 변수명 | 값 | 설명 |
|--------|-----|------|
| `MAX_MODEL_LEN` | `16384` | 최대 컨텍스트 길이 (모델 최대 32K, GPU 메모리에 따라 조절) |

> **주의: `NUM_GPU_BLOCKS_OVERRIDE`**
> - 기본값이 0으로 되어있으면 오류가 발생합니다. **반드시 삭제**하세요.
> - vLLM이 GPU 메모리에 맞게 자동 계산하므로, 이 변수는 설정하지 않는 것을 권장합니다.
>
> **주의: `VLLM_MODEL_NAME` 대소문자**
> - RunPod vLLM이 등록하는 `served_model_name`과 `.env`의 `VLLM_MODEL_NAME`이 정확히 일치해야 합니다
> - 불일치 시 500 에러가 발생합니다. RunPod 로그에서 확인하세요

설정 완료 후 **Save** → 엔드포인트가 재시작됩니다.

### 1-4. API 키 확인

RunPod 대시보드 → **Settings** → **API Keys**에서 키를 복사하세요.
엔드포인트 ID는 생성된 엔드포인트 URL에서 확인할 수 있습니다.

---

## 2. 프로젝트 설치

### 2-1. 백엔드

```bash
# 클론
git clone <repo-url> gp_claw
cd gp_claw

# 가상환경 생성 + 의존성 설치
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 2-2. 환경 변수 설정

프로젝트 루트에 `.env` 파일 생성:

```env
# RunPod vLLM
RUNPOD_API_KEY=rpa_여기에_RunPod_API_키
RUNPOD_ENDPOINT_ID=여기에_엔드포인트_ID
VLLM_MODEL_NAME=K-intelligence/Midm-2.0-Base-Instruct

# Server
PORT=8002
WORKSPACE_ROOT=~/.gp_claw/workspace

# LLM Parameters
LLM_MAX_TOKENS=8192
LLM_TEMPERATURE=0.3
```

### 2-3. 프론트엔드

```bash
cd frontend
npm install
```

---

## 3. 실행

터미널 2개를 열어서 백엔드와 프론트엔드를 각각 실행합니다.

### 터미널 1: 백엔드

```bash
source .venv/bin/activate
python -m gp_claw
# → http://localhost:8002
```

### 터미널 2: 프론트엔드

```bash
cd frontend
npm run dev
# → http://localhost:5173 (백엔드로 자동 프록시)
```

---

## 4. 사용법

### 기본 사용

1. 브라우저에서 `http://localhost:5173` 접속
2. 채팅 입력창에 자연어로 요청 (예: "파일 목록 보여줘", "매출 엑셀 만들어줘")
3. AI가 응답합니다 (토큰 단위 실시간 스트리밍)

### 작업 폴더 변경

1. 헤더 왼쪽의 **폴더 경로**를 클릭
2. 모달에서 퀵 버튼(Desktop, Documents, Downloads, Home) 선택 또는 직접 경로 입력
3. **설정** 클릭 → AI가 해당 폴더 안에서만 작업

### 위험 작업 승인

파일 쓰기/삭제/이동, 문서 생성 같은 위험 작업은 승인 카드가 표시됩니다.
**승인** 또는 **거부**를 선택하세요.

### 파일 열기

생성된 파일은 채팅에 **파일 카드**로 표시됩니다.
**열기** 버튼을 클릭하면 OS 기본 프로그램으로 파일이 열립니다.

---

## 5. 테스트

```bash
source .venv/bin/activate
python -m pytest tests/ -q
```

---

## 도구 목록

| 도구 | 분류 | 설명 |
|------|------|------|
| `file_list` | Safe | 디렉토리 파일 목록 |
| `file_read` | Safe | 파일 내용 읽기 |
| `file_search` | Safe | 파일 내용 검색 |
| `file_write` | Dangerous | 파일 쓰기 (승인 필요) |
| `file_delete` | Dangerous | 파일 삭제 (승인 필요) |
| `file_move` | Dangerous | 파일 이동/이름 변경 (승인 필요) |
| `excel_write` | Dangerous | 엑셀(.xlsx) 생성 (승인 필요) |
| `csv_write` | Dangerous | CSV 생성 (승인 필요) |
| `pdf_write` | Dangerous | PDF 생성 (승인 필요) |
| `pptx_write` | Dangerous | 파워포인트(.pptx) 생성 (승인 필요) |
| `file_open` | Dangerous | 파일을 OS 기본 프로그램으로 열기 (승인 필요) |
