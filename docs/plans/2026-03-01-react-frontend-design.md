# GP Claw React Frontend Design

> 2026-03-01 | Phase 3: React 프론트엔드

## Goal

백엔드 WebSocket API(`ws://localhost:8000/ws/{session_id}`)와 연결되는 채팅 UI 구현.
사용자 메시지 전송, AI 응답 표시, Dangerous 도구 승인/거부 워크플로우 지원.

## Tech Stack

- **Vite + React 19 + TypeScript**
- **shadcn/ui + Tailwind CSS** (다크모드 only)
- 상태 관리: React useState/useReducer (별도 라이브러리 불필요)

## Architecture

Single-Page Chat App. 라우팅 없음.

```
App.tsx
├── Header (GP Claw 로고 + ConnectionStatus)
├── ChatContainer
│   ├── ChatMessage (user)
│   ├── ChatMessage (assistant)
│   ├── ApprovalCard (dangerous tool 호출 시)
│   └── ... (자동 스크롤)
├── ChatInput (textarea + 전송 버튼)
```

## WebSocket Protocol

### Client → Server

| type | payload |
|------|---------|
| `user_message` | `{ content: string }` |
| `approval_response` | `{ decision: "approved" \| "rejected" }` |
| `ping` | (없음) |

### Server → Client

| type | payload |
|------|---------|
| `assistant_message` | `{ content: string }` |
| `approval_request` | `{ tool_calls: [{ tool, args, preview }] }` |
| `error` | `{ content: string }` |
| `pong` | (없음) |

## Components

| 컴포넌트 | 역할 |
|---------|------|
| `App.tsx` | 레이아웃, WebSocket 연결, 상태 관리 |
| `ChatContainer` | 메시지 리스트 렌더링, 자동 스크롤 |
| `ChatMessage` | user/assistant 메시지 버블 |
| `ApprovalCard` | 도구명 + preview + 승인/거부 버튼 |
| `ChatInput` | textarea + 전송. Enter=전송, Shift+Enter=줄바꿈 |
| `ConnectionStatus` | 연결 상태 표시 (badge) |

## State

```typescript
type Message =
  | { id: string; type: "user"; content: string }
  | { id: string; type: "assistant"; content: string }
  | { id: string; type: "approval_request"; toolCalls: ToolCall[]; status: "pending" | "approved" | "rejected" }
  | { id: string; type: "error"; content: string }

interface AppState {
  messages: Message[]
  isConnected: boolean
  isWaitingResponse: boolean
  isWaitingApproval: boolean
}
```

## useWebSocket Hook

- 세션 ID: `crypto.randomUUID()` → `sessionStorage` 저장
- 자동 재연결: 지수 백오프 (1s, 2s, 4s, 8s, max 30s)
- ping/pong: 30초 간격 킵얼라이브

## Approval Flow

1. `approval_request` 수신 → ApprovalCard 렌더 + 입력 비활성화
2. 승인/거부 클릭 → `approval_response` 전송
3. 다음 `approval_request` 또는 `assistant_message` 대기
4. 최종 응답 → 입력 재활성화

## Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/              # shadcn/ui
│   │   ├── ChatContainer.tsx
│   │   ├── ChatMessage.tsx
│   │   ├── ApprovalCard.tsx
│   │   ├── ChatInput.tsx
│   │   └── ConnectionStatus.tsx
│   ├── hooks/
│   │   └── useWebSocket.ts
│   ├── lib/
│   │   └── utils.ts
│   ├── types.ts
│   ├── App.tsx
│   ├── App.css
│   └── main.tsx
├── index.html
├── package.json
├── tailwind.config.ts
├── tsconfig.json
└── vite.config.ts
```

## Decisions

- **다크모드 only**: 사내 도구, 토글 불필요
- **라우팅 없음**: 현재 채팅 하나만 필요. YAGNI.
- **상태 라이브러리 없음**: 단일 페이지에 useState/useReducer 충분
- **스트리밍 미지원**: 백엔드가 완성 메시지 단위 전송 (ainvoke)
