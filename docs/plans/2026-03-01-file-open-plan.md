# 파일 열기 기능 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 생성된 파일을 PC의 기본 프로그램으로 열 수 있게 하기. AI 도구 + 프론트엔드 버튼 두 경로 지원.

**Architecture:** `file_open` Dangerous 도구 추가 + WebSocket `open_file` 메시지 타입으로 프론트엔드 직접 열기 지원. 도구 결과에 파일 경로가 포함되면 프론트엔드에서 파일 카드를 렌더링.

**Tech Stack:** Python subprocess/os.startfile (OS별 분기), React 컴포넌트

---

## Task 1: `file_open` 도구 추가

**Files:**
- Modify: `src/gp_claw/tools/office_file.py`

**Step 1: office_file.py에 `_open_with_os` 헬퍼 + `file_open` 도구 추가**

`create_office_tools` 함수 위에 모듈 레벨 헬퍼 추가:

```python
import platform
import subprocess

def _open_with_os(filepath: str) -> None:
    """OS 기본 프로그램으로 파일 열기."""
    system = platform.system()
    if system == "Darwin":
        subprocess.Popen(["open", filepath])
    elif system == "Windows":
        import os
        os.startfile(filepath)
    else:
        subprocess.Popen(["xdg-open", filepath])
```

`create_office_tools` 반환 리스트에 `file_open` 도구 추가:

```python
@tool
def file_open(path: str) -> dict:
    """지정된 파일을 PC의 기본 프로그램으로 엽니다. (승인 필요)

    Args:
        path: 워크스페이스 내 파일 경로
    """
    validated = validate_path(path, workspace_root)
    if not validated.exists():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")
    _open_with_os(str(validated))
    return {
        "path": str(validated),
        "action": "opened",
        "filename": validated.name,
    }
```

반환 리스트: `return [excel_write, csv_write, pdf_write, pptx_write, file_open]`

**Step 2: Commit**

```bash
git add src/gp_claw/tools/office_file.py
git commit -m "feat: file_open 도구 추가 (OS 기본 프로그램으로 파일 열기)"
```

---

## Task 2: `file_open` 테스트

**Files:**
- Modify: `tests/test_office_tools.py`

**Step 1: file_open 테스트 추가**

```python
@pytest.fixture
def file_open(tools):
    return tools[4]


def test_file_open_existing_file(workspace, file_open, monkeypatch):
    (workspace / "test.txt").write_text("hello")
    monkeypatch.setattr("gp_claw.tools.office_file._open_with_os", lambda p: None)
    result = file_open.invoke({"path": "test.txt"})
    assert result["action"] == "opened"
    assert result["filename"] == "test.txt"


def test_file_open_nonexistent_raises(workspace, file_open):
    with pytest.raises(Exception):
        file_open.invoke({"path": "no_such_file.txt"})


def test_file_open_blocks_outside_workspace(workspace, file_open):
    with pytest.raises(Exception):
        file_open.invoke({"path": "/etc/passwd"})
```

**Step 2: 테스트 실행**

```bash
python -m pytest tests/test_office_tools.py -v
```

**Step 3: Commit**

```bash
git add tests/test_office_tools.py
git commit -m "test: file_open 도구 테스트 추가"
```

---

## Task 3: WebSocket `open_file` 메시지 핸들러

**Files:**
- Modify: `src/gp_claw/server.py`

**Step 1: server.py에 `open_file` 핸들러 추가**

`websocket_endpoint` 함수 내, `elif data.get("type") == "user_message":` 블록 앞에 추가:

```python
elif data.get("type") == "open_file":
    from gp_claw.security import validate_path, SecurityViolation
    from gp_claw.tools.office_file import _open_with_os
    raw_path = data.get("path", "")
    try:
        validated = validate_path(raw_path, session_workspace)
        if not validated.exists():
            await websocket.send_json({
                "type": "error",
                "content": f"파일을 찾을 수 없습니다: {raw_path}",
            })
        else:
            _open_with_os(str(validated))
            await websocket.send_json({
                "type": "file_opened",
                "path": str(validated),
                "filename": validated.name,
            })
    except SecurityViolation as e:
        await websocket.send_json({
            "type": "error",
            "content": str(e),
        })
```

**Step 2: Commit**

```bash
git add src/gp_claw/server.py
git commit -m "feat: WebSocket open_file 메시지 핸들러 추가"
```

---

## Task 4: 프론트엔드 타입 + WebSocket 훅 업데이트

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/hooks/useWebSocket.ts`

**Step 1: types.ts에 타입 추가**

WsSend에 추가:
```typescript
| { type: "open_file"; path: string }
```

WsReceive에 추가:
```typescript
| { type: "file_opened"; path: string; filename: string }
```

**Step 2: useWebSocket.ts에 `openFile` 함수 + 핸들러 추가**

`UseWebSocketReturn` 인터페이스에 추가:
```typescript
openFile: (path: string) => void
```

`handleMessage` switch에 추가:
```typescript
case "file_opened":
  // 알림 없이 조용히 처리 (OS가 파일을 열어줌)
  break
```

`openFile` 함수 정의:
```typescript
const openFile = useCallback(
  (path: string) => {
    send({ type: "open_file", path })
  },
  [send]
)
```

반환 객체에 `openFile` 추가.

**Step 3: Commit**

```bash
git add frontend/src/types.ts frontend/src/hooks/useWebSocket.ts
git commit -m "feat: 프론트엔드 open_file WebSocket 프로토콜 추가"
```

---

## Task 5: 파일 카드 컴포넌트 + ChatMessage 통합

**Files:**
- Create: `frontend/src/components/FileCard.tsx`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/components/ChatMessage.tsx`
- Modify: `frontend/src/components/ChatContainer.tsx`

**Step 1: types.ts에 FileCardMessage 타입 추가**

```typescript
export interface FileCardMessage {
  id: string
  type: "file_card"
  filename: string
  path: string
  sizeBytes: number
  timestamp: number
}
```

`Message` union에 `FileCardMessage` 추가:
```typescript
export type Message = UserMessage | AssistantMessage | ApprovalRequestMessage | ErrorMessage | FileCardMessage
```

**Step 2: FileCard.tsx 생성**

```tsx
import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { FileSpreadsheet, FileText, File, Presentation, FolderOpen } from "lucide-react"
import type { FileCardMessage } from "@/types"

interface FileCardProps {
  message: FileCardMessage
  onOpen: (path: string) => void
}

function getFileIcon(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase()
  switch (ext) {
    case "xlsx": case "xls": case "csv":
      return <FileSpreadsheet className="h-5 w-5 text-green-400" />
    case "pdf":
      return <FileText className="h-5 w-5 text-red-400" />
    case "pptx": case "ppt":
      return <Presentation className="h-5 w-5 text-orange-400" />
    default:
      return <File className="h-5 w-5 text-blue-400" />
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function FileCard({ message, onOpen }: FileCardProps) {
  return (
    <div className="flex w-full justify-start">
      <Card className="max-w-[80%] border-border/50 bg-secondary/50">
        <CardContent className="flex items-center gap-3 p-3">
          {getFileIcon(message.filename)}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{message.filename}</p>
            <p className="text-xs text-muted-foreground">{formatSize(message.sizeBytes)}</p>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="shrink-0"
            onClick={() => onOpen(message.path)}
          >
            <FolderOpen className="mr-1 h-3 w-3" />
            열기
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
```

**Step 3: useWebSocket.ts — 도구 결과에서 파일 카드 감지**

`assistant_done` 케이스를 수정하여, 직전 assistant 메시지에서 도구 결과 파일 경로를 파싱.

대신 더 간단한 접근: 서버가 도구 실행 완료 후 파일 정보를 `file_created` 메시지로 보내기.

server.py의 approval 승인 후 처리 부분에서, 도구 결과에 `action: created`가 있으면 `file_created` 메시지를 별도 전송:

`server.py` 수정 — approval 승인 후 resume 스트리밍 완료 시, 최종 state에서 도구 결과 확인:

```python
# _stream_agent_response 이후, assistant_done 전에:
final_state = await session_agent.aget_state(config)
msgs = final_state.values.get("messages", [])
for msg in msgs:
    if hasattr(msg, "name") and hasattr(msg, "content"):
        try:
            import json as _json
            result = _json.loads(msg.content) if isinstance(msg.content, str) else msg.content
            if isinstance(result, dict) and result.get("action") == "created":
                await websocket.send_json({
                    "type": "file_created",
                    "path": result.get("path", ""),
                    "filename": Path(result.get("path", "")).name,
                    "size_bytes": result.get("size_bytes", 0),
                })
        except (ValueError, TypeError):
            pass
```

WsReceive 타입에 추가:
```typescript
| { type: "file_created"; path: string; filename: string; size_bytes: number }
```

handleMessage에서 `file_created` 수신 시 FileCardMessage 추가:
```typescript
case "file_created":
  setMessages((prev) => [
    ...prev,
    {
      id: crypto.randomUUID(),
      type: "file_card",
      filename: data.filename,
      path: data.path,
      sizeBytes: data.size_bytes,
      timestamp: Date.now(),
    },
  ])
  break
```

**Step 4: ChatContainer.tsx에 FileCard 렌더링 추가**

기존 메시지 렌더링 분기에 `file_card` 타입 추가:
```tsx
{msg.type === "file_card" && (
  <FileCard message={msg} onOpen={onOpenFile} />
)}
```

`ChatContainer`의 props에 `onOpenFile` 추가, App.tsx에서 전달.

**Step 5: 빌드 검증**

```bash
cd frontend && npm run build
```

**Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: 파일 카드 UI + 열기 버튼 구현"
```

---

## Task 6: 시스템 프롬프트에 file_open 안내 추가

**Files:**
- Modify: `src/gp_claw/llm.py`

**Step 1: 프롬프트 수정**

OFFICE TOOLS GUIDE 섹션 마지막에 추가:
```
- 파일을 열어달라는 요청 → file_open 도구 사용. 예: "방금 만든 엑셀 열어줘" → file_open 호출.
```

**Step 2: Commit**

```bash
git add src/gp_claw/llm.py
git commit -m "feat: 시스템 프롬프트에 file_open 가이드 추가"
```

---

## Task 7: 전체 검증

**Step 1: Backend 테스트**

```bash
python -m pytest tests/ -q
```

**Step 2: Frontend 빌드**

```bash
cd frontend && npm run build
```
