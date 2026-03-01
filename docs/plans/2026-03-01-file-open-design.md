# Phase 5.1: 파일 열기 기능

**Goal:** 생성된 파일을 PC의 기본 프로그램으로 열 수 있게 하기.
사용자가 직접 "열기" 버튼 클릭 또는 AI에게 "열어줘" 요청 모두 지원.

**OS 지원:** macOS (`open`), Windows (`os.startfile`), Linux (`xdg-open`)

---

## 아키텍처

```
[AI가 "열어줘" 요청 받음]           [프론트엔드 "열기" 버튼 클릭]
       ↓                                    ↓
 file_open 도구 (Dangerous)         WS: {"type": "open_file", "path": "..."}
       ↓                                    ↓
  승인 카드 → 승인                   validate_path 검증
       ↓                                    ↓
  OS open 실행 ←←←←←←←←←←←←←←←←←  OS open 실행
```

## 변경 파일

### Backend
- `src/gp_claw/tools/office_file.py` — `file_open(path)` 도구 추가
- `src/gp_claw/server.py` — `open_file` WebSocket 메시지 핸들러 추가
- `src/gp_claw/llm.py` — 시스템 프롬프트에 file_open 안내 추가

### Frontend
- `frontend/src/types.ts` — `FileCard`, `open_file` 메시지 타입 추가
- `frontend/src/components/ChatMessage.tsx` — 파일 카드 렌더링
- `frontend/src/hooks/useWebSocket.ts` — `open_file` 전송 + 도구 결과에서 파일 카드 감지

### Tests
- `tests/test_office_tools.py` — `file_open` 테스트 추가

## file_open 도구 상세

```python
import platform, subprocess, os

def _open_with_os(filepath: str):
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["open", filepath])
    elif system == "Windows":
        os.startfile(filepath)
    else:
        subprocess.run(["xdg-open", filepath])
```

- Dangerous 분류 (승인 필요)
- `validate_path`로 경로 검증
- 파일 존재 여부 체크

## 파일 카드 UI

도구 결과에 `"action": "created"` 또는 `"action": "opened"` 가 있으면 파일 카드 표시:
- 파일 아이콘 (확장자별)
- 파일명 + 크기
- [열기] 버튼 → WS `open_file` 전송

## 프론트엔드 직접 열기 (open_file WS)

- 사용자가 버튼 클릭 = 의도 확인이므로 별도 승인 없음
- 서버에서 `validate_path` 검증 후 OS open 실행
- 결과: `{"type": "file_opened", "path": "..."}` 또는 `{"type": "error", ...}`
