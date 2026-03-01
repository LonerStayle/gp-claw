# Phase 4: 폴더 선택 기능 설계 + 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 프론트엔드에서 사용자가 AI가 작업할 폴더를 직접 선택할 수 있는 기능. 워크스페이스를 고정 경로 대신 사용자가 지정한 폴더로 동적 변경.

**Architecture:** 프론트엔드 설정 패널에서 폴더 경로 입력/선택 → WebSocket으로 백엔드에 전송 → 백엔드가 workspace_root를 동적으로 변경하여 도구에 반영.

**Tech Stack:** React (기존), shadcn/ui Dialog, Backend REST 또는 WebSocket 확장

---

## 설계

### 사용자 흐름

```
1. 프론트엔드 헤더에 [폴더 설정] 버튼
2. 클릭 → 모달 (Dialog) 열림
3. 경로 직접 입력 (예: ~/Desktop, /Users/goldenplanet/Documents)
   또는 자주 쓰는 폴더 퀵 버튼 (Desktop, Documents, Downloads)
4. "설정" 클릭 → 백엔드에 workspace 변경 요청
5. 헤더에 현재 작업 폴더 표시 (예: "📁 ~/Desktop")
6. 이후 AI는 해당 폴더 안에서만 작업
```

### 프로토콜 확장

```json
// Client → Server: 워크스페이스 변경
{"type": "set_workspace", "path": "/Users/goldenplanet/Desktop"}

// Server → Client: 변경 확인
{"type": "workspace_changed", "path": "/Users/goldenplanet/Desktop", "display": "~/Desktop"}

// Server → Client: 변경 실패 (경로 없음 등)
{"type": "workspace_error", "content": "경로를 찾을 수 없습니다: /invalid/path"}
```

### 백엔드 변경

1. **세션별 workspace_root**: 현재 전역 workspace_root를 세션(thread_id)별로 관리
2. **`server.py`**: `set_workspace` 메시지 처리 추가
3. **`security.py`**: `validate_path`가 세션별 workspace_root를 받도록 (이미 파라미터로 받고 있으므로 변경 최소)
4. **도구 재생성**: workspace 변경 시 `create_tool_registry(new_path)` 호출하여 새 도구 세트 생성

### 프론트엔드 변경

1. **`FolderPicker.tsx`**: 폴더 설정 모달 컴포넌트
2. **`useWebSocket.ts`**: `set_workspace` 메시지 전송 + `workspace_changed` 수신 처리
3. **`App.tsx`**: 헤더에 현재 폴더 표시 + FolderPicker 연동
4. **`types.ts`**: 새 메시지 타입 추가

### 보안 고려

- `validate_path`의 기존 시스템 경로 차단 유지 (`/etc`, `/usr`, `.ssh` 등)
- workspace 변경 시 경로 존재 여부 + 읽기 권한 검증
- 상대 경로(`~`) 확장 처리

---

## 구현 계획

### Task 1: 백엔드 — 세션별 workspace 관리

**Files:**
- Modify: `src/gp_claw/server.py`

**Step 1: WebSocket 엔드포인트에 세션별 workspace 상태 추가**

`server.py`의 `websocket_endpoint` 함수에 `workspace_root` 변수를 추가하고, `set_workspace` 메시지 핸들러 구현:

```python
# websocket_endpoint 내부
workspace_root = str(Path(default_workspace).expanduser().resolve())
current_registry = registry
current_agent = agent

# set_workspace 핸들러
elif data.get("type") == "set_workspace":
    new_path = Path(data.get("path", "")).expanduser().resolve()
    if not new_path.exists():
        await websocket.send_json({
            "type": "workspace_error",
            "content": f"경로를 찾을 수 없습니다: {data.get('path')}",
        })
    elif not new_path.is_dir():
        await websocket.send_json({
            "type": "workspace_error",
            "content": f"디렉토리가 아닙니다: {data.get('path')}",
        })
    else:
        workspace_root = str(new_path)
        current_registry = create_tool_registry(workspace_root)
        current_agent = create_agent(llm, registry=current_registry, checkpointer=checkpointer)
        display = str(new_path).replace(str(Path.home()), "~")
        await websocket.send_json({
            "type": "workspace_changed",
            "path": str(new_path),
            "display": display,
        })
```

**Step 2: Commit**

```bash
git add src/gp_claw/server.py
git commit -m "feat: 세션별 workspace 동적 변경 (set_workspace 메시지)"
```

---

### Task 2: 프론트엔드 — 타입 + useWebSocket 확장

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/hooks/useWebSocket.ts`

**Step 1: 새 메시지 타입 추가**

`types.ts`에 추가:
```typescript
export type WsSend =
  | { type: "user_message"; content: string }
  | { type: "approval_response"; decision: "approved" | "rejected" }
  | { type: "set_workspace"; path: string }
  | { type: "ping" }

export type WsReceive =
  | { type: "assistant_message"; content: string }
  | { type: "approval_request"; tool_calls: ToolCall[] }
  | { type: "error"; content: string }
  | { type: "workspace_changed"; path: string; display: string }
  | { type: "workspace_error"; content: string }
  | { type: "pong" }
```

**Step 2: useWebSocket에 workspace 상태 + setWorkspace 함수 추가**

```typescript
const [currentWorkspace, setCurrentWorkspace] = useState<string | null>(null)

// handleMessage에 추가
case "workspace_changed":
  setCurrentWorkspace(data.display)
  break
case "workspace_error":
  setMessages(prev => [...prev, { id: crypto.randomUUID(), type: "error", content: data.content }])
  break

// 새 함수
const setWorkspace = useCallback((path: string) => {
  send({ type: "set_workspace", path })
}, [send])
```

**Step 3: Commit**

```bash
git add frontend/src/types.ts frontend/src/hooks/useWebSocket.ts
git commit -m "feat: workspace 변경 프로토콜 (types + useWebSocket)"
```

---

### Task 3: 프론트엔드 — FolderPicker 컴포넌트

**Files:**
- Create: `frontend/src/components/FolderPicker.tsx`

**Step 1: shadcn Dialog 컴포넌트 추가**

```bash
# shadcn/ui의 Dialog 의존성 설치
npm install @radix-ui/react-dialog
```

`frontend/src/components/ui/dialog.tsx` 생성 (shadcn Dialog)

**Step 2: FolderPicker 컴포넌트 구현**

```typescript
// 주요 기능:
// - 경로 입력 필드 (텍스트)
// - 퀵 버튼: Desktop, Documents, Downloads, Home
// - 현재 워크스페이스 표시
// - "설정" 버튼으로 적용
```

**Step 3: Commit**

```bash
git add frontend/src/components/FolderPicker.tsx frontend/src/components/ui/dialog.tsx
git commit -m "feat: FolderPicker 폴더 선택 모달 컴포넌트"
```

---

### Task 4: 프론트엔드 — App.tsx 통합

**Files:**
- Modify: `frontend/src/App.tsx`

**Step 1: 헤더에 현재 폴더 표시 + FolderPicker 버튼 추가**

```typescript
// 헤더에 추가:
// - 현재 폴더 표시 (예: "📁 ~/Desktop")
// - [폴더 변경] 버튼 → FolderPicker 모달 열기
```

**Step 2: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: 헤더에 폴더 선택 UI 통합"
```

---

### Task 5: 빌드 검증 + E2E 테스트

**Step 1: Frontend 빌드**

```bash
cd frontend && npm run build
```

**Step 2: 수동 E2E 테스트**

1. 백엔드 + 프론트엔드 실행
2. 기본 워크스페이스 확인 (~/. gp_claw/workspace)
3. 폴더 변경 → ~/Desktop 선택
4. "파일 목록 보여줘" → Desktop 파일 표시 확인
5. 존재하지 않는 경로 → 에러 메시지 확인

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: Phase 4 폴더 선택 기능 완성"
```
