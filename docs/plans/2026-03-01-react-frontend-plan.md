# React Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** GP Claw 백엔드 WebSocket API와 연결되는 채팅 UI 구현 (메시지, 승인 카드, 연결 상태)

**Architecture:** Single-Page Chat App. Vite + React + TypeScript. shadcn/ui + Tailwind (다크모드 only). useWebSocket 훅으로 WS 연결 관리. 라우팅 없음.

**Tech Stack:** Vite, React 19, TypeScript, Tailwind CSS 4, shadcn/ui, Vitest

**Backend WebSocket:** `ws://localhost:8000/ws/{session_id}` — 메시지: `user_message`, `assistant_message`, `approval_request`, `approval_response`, `ping`/`pong`, `error`

---

### Task 1: Scaffold Vite + React + TypeScript Project

**Files:**
- Create: `frontend/` (Vite scaffold)
- Create: `frontend/vite.config.ts` (proxy 설정 포함)

**Step 1: Create Vite project**

```bash
cd /Users/goldenplanet/jinsup_space/gp_claw
npm create vite@latest frontend -- --template react-ts
```

**Step 2: Install dependencies**

```bash
cd frontend
npm install
```

**Step 3: Verify dev server starts**

```bash
npm run dev -- --port 5173
# 브라우저에서 http://localhost:5173 확인 후 Ctrl+C
```

**Step 4: Configure Vite proxy for backend WebSocket**

`frontend/vite.config.ts`:
```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
      '/health': {
        target: 'http://localhost:8000',
      },
    },
  },
})
```

**Step 5: Clean up default Vite files**

- Delete `src/App.css` contents (will replace)
- Delete `src/assets/` directory
- Simplify `src/App.tsx` to minimal placeholder

**Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold Vite + React + TypeScript frontend"
```

---

### Task 2: Setup Tailwind CSS + shadcn/ui

**Files:**
- Modify: `frontend/package.json` (new deps)
- Create: `frontend/src/index.css` (Tailwind directives + dark theme)
- Create: `frontend/components.json` (shadcn config)
- Create: `frontend/src/lib/utils.ts`

**Step 1: Install Tailwind CSS v4**

```bash
cd frontend
npm install tailwindcss @tailwindcss/vite
```

**Step 2: Add Tailwind Vite plugin**

Update `frontend/vite.config.ts` plugins array:
```typescript
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // ... rest
})
```

**Step 3: Setup CSS with Tailwind directives + dark theme variables**

`frontend/src/index.css`:
```css
@import "tailwindcss";

@custom-variant dark (&:is(.dark *));

:root {
  --background: 224 71% 4%;
  --foreground: 213 31% 91%;
  --card: 224 71% 4%;
  --card-foreground: 213 31% 91%;
  --popover: 224 71% 4%;
  --popover-foreground: 213 31% 91%;
  --primary: 210 40% 98%;
  --primary-foreground: 222.2 47.4% 11.2%;
  --secondary: 222.2 47.4% 11.2%;
  --secondary-foreground: 210 40% 98%;
  --muted: 223 47% 11%;
  --muted-foreground: 215.4 16.3% 56.9%;
  --accent: 216 34% 17%;
  --accent-foreground: 210 40% 98%;
  --destructive: 0 63% 31%;
  --destructive-foreground: 210 40% 98%;
  --border: 216 34% 17%;
  --input: 216 34% 17%;
  --ring: 216 34% 17%;
  --radius: 0.5rem;
  --warning: 38 92% 50%;
  --warning-foreground: 0 0% 0%;
}

body {
  background-color: hsl(var(--background));
  color: hsl(var(--foreground));
  font-family: system-ui, -apple-system, sans-serif;
}
```

**Step 4: Install shadcn/ui dependencies**

```bash
npm install class-variance-authority clsx tailwind-merge lucide-react
```

**Step 5: Create utils**

`frontend/src/lib/utils.ts`:
```typescript
import { type ClassValue, clsx } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
```

**Step 6: Add shadcn Button component**

`frontend/src/components/ui/button.tsx`:
```typescript
import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline: "border border-input bg-background hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-9 rounded-md px-3",
        lg: "h-11 rounded-md px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button, buttonVariants }
```

```bash
npm install @radix-ui/react-slot
```

**Step 7: Add shadcn Card component**

`frontend/src/components/ui/card.tsx`:
```typescript
import * as React from "react"
import { cn } from "@/lib/utils"

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("rounded-lg border border-border bg-card text-card-foreground shadow-sm", className)} {...props} />
  )
)
Card.displayName = "Card"

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 p-4", className)} {...props} />
  )
)
CardHeader.displayName = "CardHeader"

const CardTitle = React.forwardRef<HTMLParagraphElement, React.HTMLAttributes<HTMLHeadingElement>>(
  ({ className, ...props }, ref) => (
    <h3 ref={ref} className={cn("text-sm font-semibold leading-none tracking-tight", className)} {...props} />
  )
)
CardTitle.displayName = "CardTitle"

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-4 pt-0", className)} {...props} />
  )
)
CardContent.displayName = "CardContent"

const CardFooter = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex items-center p-4 pt-0", className)} {...props} />
  )
)
CardFooter.displayName = "CardFooter"

export { Card, CardHeader, CardTitle, CardContent, CardFooter }
```

**Step 8: Add shadcn Badge component**

`frontend/src/components/ui/badge.tsx`:
```typescript
import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
        outline: "text-foreground",
        warning: "border-transparent bg-[hsl(var(--warning))] text-[hsl(var(--warning-foreground))]",
        success: "border-transparent bg-green-600 text-white",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />
}

export { Badge, badgeVariants }
```

**Step 9: Verify build passes**

```bash
npm run build
```

**Step 10: Commit**

```bash
git add frontend/
git commit -m "feat: setup Tailwind CSS v4 + shadcn/ui components"
```

---

### Task 3: TypeScript Types

**Files:**
- Create: `frontend/src/types.ts`

**Step 1: Define message and WebSocket types**

`frontend/src/types.ts`:
```typescript
// --- Tool Call ---
export interface ToolCall {
  tool: string
  args: Record<string, unknown>
  preview: string
}

// --- Messages (UI state) ---
export interface UserMessage {
  id: string
  type: "user"
  content: string
}

export interface AssistantMessage {
  id: string
  type: "assistant"
  content: string
}

export interface ApprovalRequestMessage {
  id: string
  type: "approval_request"
  toolCalls: ToolCall[]
  status: "pending" | "approved" | "rejected"
}

export interface ErrorMessage {
  id: string
  type: "error"
  content: string
}

export type Message = UserMessage | AssistantMessage | ApprovalRequestMessage | ErrorMessage

// --- WebSocket protocol (wire format) ---
export type WsSend =
  | { type: "user_message"; content: string }
  | { type: "approval_response"; decision: "approved" | "rejected" }
  | { type: "ping" }

export type WsReceive =
  | { type: "assistant_message"; content: string }
  | { type: "approval_request"; tool_calls: ToolCall[] }
  | { type: "error"; content: string }
  | { type: "pong" }

// --- Connection status ---
export type ConnectionStatus = "connected" | "disconnected" | "reconnecting"
```

**Step 2: Commit**

```bash
git add frontend/src/types.ts
git commit -m "feat: TypeScript type definitions for messages and WebSocket protocol"
```

---

### Task 4: useWebSocket Hook

**Files:**
- Create: `frontend/src/hooks/useWebSocket.ts`

**Step 1: Implement useWebSocket hook**

`frontend/src/hooks/useWebSocket.ts`:
```typescript
import { useCallback, useEffect, useRef, useState } from "react"
import type { ConnectionStatus, Message, WsReceive, WsSend } from "@/types"

function generateSessionId(): string {
  const stored = sessionStorage.getItem("gp-claw-session-id")
  if (stored) return stored
  const id = crypto.randomUUID()
  sessionStorage.setItem("gp-claw-session-id", id)
  return id
}

interface UseWebSocketReturn {
  messages: Message[]
  connectionStatus: ConnectionStatus
  isWaitingResponse: boolean
  isWaitingApproval: boolean
  sendMessage: (content: string) => void
  sendApproval: (decision: "approved" | "rejected") => void
}

export function useWebSocket(): UseWebSocketReturn {
  const [messages, setMessages] = useState<Message[]>([])
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("disconnected")
  const [isWaitingResponse, setIsWaitingResponse] = useState(false)
  const [isWaitingApproval, setIsWaitingApproval] = useState(false)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>()
  const pingTimerRef = useRef<ReturnType<typeof setInterval>>()

  const send = useCallback((data: WsSend) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  const handleMessage = useCallback((event: MessageEvent) => {
    const data: WsReceive = JSON.parse(event.data)

    switch (data.type) {
      case "assistant_message":
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), type: "assistant", content: data.content },
        ])
        setIsWaitingResponse(false)
        setIsWaitingApproval(false)
        break

      case "approval_request":
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            type: "approval_request",
            toolCalls: data.tool_calls,
            status: "pending",
          },
        ])
        setIsWaitingResponse(false)
        setIsWaitingApproval(true)
        break

      case "error":
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), type: "error", content: data.content },
        ])
        setIsWaitingResponse(false)
        setIsWaitingApproval(false)
        break

      case "pong":
        break
    }
  }, [])

  const connect = useCallback(() => {
    const sessionId = generateSessionId()
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
    const wsUrl = `${protocol}//${window.location.host}/ws/${sessionId}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnectionStatus("connected")
      reconnectAttemptRef.current = 0

      // Ping keepalive
      pingTimerRef.current = setInterval(() => {
        send({ type: "ping" })
      }, 30_000)
    }

    ws.onmessage = handleMessage

    ws.onclose = () => {
      setConnectionStatus("disconnected")
      if (pingTimerRef.current) clearInterval(pingTimerRef.current)

      // Exponential backoff reconnect
      const delay = Math.min(1000 * 2 ** reconnectAttemptRef.current, 30_000)
      reconnectAttemptRef.current += 1
      setConnectionStatus("reconnecting")
      reconnectTimerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [handleMessage, send])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      if (pingTimerRef.current) clearInterval(pingTimerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  const sendMessage = useCallback(
    (content: string) => {
      if (!content.trim()) return
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), type: "user", content },
      ])
      setIsWaitingResponse(true)
      send({ type: "user_message", content })
    },
    [send]
  )

  const sendApproval = useCallback(
    (decision: "approved" | "rejected") => {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.type === "approval_request" && msg.status === "pending"
            ? { ...msg, status: decision }
            : msg
        )
      )
      setIsWaitingApproval(false)
      setIsWaitingResponse(true)
      send({ type: "approval_response", decision })
    },
    [send]
  )

  return {
    messages,
    connectionStatus,
    isWaitingResponse,
    isWaitingApproval,
    sendMessage,
    sendApproval,
  }
}
```

**Step 2: Commit**

```bash
git add frontend/src/hooks/useWebSocket.ts
git commit -m "feat: useWebSocket hook with auto-reconnect and approval flow"
```

---

### Task 5: ChatMessage Component

**Files:**
- Create: `frontend/src/components/ChatMessage.tsx`

**Step 1: Implement ChatMessage**

`frontend/src/components/ChatMessage.tsx`:
```typescript
import { cn } from "@/lib/utils"
import type { AssistantMessage, ErrorMessage, UserMessage } from "@/types"

interface ChatMessageProps {
  message: UserMessage | AssistantMessage | ErrorMessage
}

export function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.type === "user"
  const isError = message.type === "error"

  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser && "bg-primary text-primary-foreground",
          !isUser && !isError && "bg-secondary text-secondary-foreground",
          isError && "bg-destructive/20 text-red-400 border border-destructive/30"
        )}
      >
        <p className="whitespace-pre-wrap break-words">{message.content}</p>
      </div>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/ChatMessage.tsx
git commit -m "feat: ChatMessage component with user/assistant/error styles"
```

---

### Task 6: ApprovalCard Component

**Files:**
- Create: `frontend/src/components/ApprovalCard.tsx`

**Step 1: Implement ApprovalCard**

`frontend/src/components/ApprovalCard.tsx`:
```typescript
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import type { ApprovalRequestMessage } from "@/types"
import { ShieldAlert, Check, X } from "lucide-react"

interface ApprovalCardProps {
  message: ApprovalRequestMessage
  onApprove: () => void
  onReject: () => void
}

export function ApprovalCard({ message, onApprove, onReject }: ApprovalCardProps) {
  const isPending = message.status === "pending"

  return (
    <div className="flex w-full justify-start">
      <Card className="w-full max-w-[90%] border-[hsl(var(--warning))]/30 bg-[hsl(var(--warning))]/5">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-[hsl(var(--warning))]">
            <ShieldAlert className="h-4 w-4" />
            승인 필요
            {!isPending && (
              <Badge variant={message.status === "approved" ? "success" : "destructive"}>
                {message.status === "approved" ? "승인됨" : "거부됨"}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {message.toolCalls.map((tc, i) => (
            <div key={i} className="space-y-1">
              <Badge variant="outline" className="font-mono text-xs">
                {tc.tool}
              </Badge>
              <pre className="mt-1 rounded-md bg-black/30 p-3 text-xs text-muted-foreground overflow-x-auto whitespace-pre-wrap">
                {tc.preview}
              </pre>
            </div>
          ))}
        </CardContent>
        {isPending && (
          <CardFooter className="gap-2">
            <Button size="sm" onClick={onApprove} className="bg-green-600 hover:bg-green-700 text-white">
              <Check className="mr-1 h-3 w-3" />
              승인
            </Button>
            <Button size="sm" variant="destructive" onClick={onReject}>
              <X className="mr-1 h-3 w-3" />
              거부
            </Button>
          </CardFooter>
        )}
      </Card>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/ApprovalCard.tsx
git commit -m "feat: ApprovalCard component with approve/reject buttons"
```

---

### Task 7: ChatInput Component

**Files:**
- Create: `frontend/src/components/ChatInput.tsx`

**Step 1: Implement ChatInput**

`frontend/src/components/ChatInput.tsx`:
```typescript
import { useState, useRef, useCallback } from "react"
import { Button } from "@/components/ui/button"
import { SendHorizonal } from "lucide-react"

interface ChatInputProps {
  onSend: (content: string) => void
  disabled: boolean
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [input, setInput] = useState("")
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const handleSend = useCallback(() => {
    const trimmed = input.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setInput("")
    // Reset textarea height
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
    }
  }, [input, disabled, onSend])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    // Auto-resize
    const el = e.target
    el.style.height = "auto"
    el.style.height = Math.min(el.scrollHeight, 200) + "px"
  }

  return (
    <div className="flex items-end gap-2 border-t border-border bg-background p-4">
      <textarea
        ref={textareaRef}
        value={input}
        onChange={handleInput}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? "응답 대기 중..." : "메시지를 입력하세요..."}
        disabled={disabled}
        rows={1}
        className="flex-1 resize-none rounded-lg border border-input bg-secondary px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
      />
      <Button
        size="icon"
        onClick={handleSend}
        disabled={disabled || !input.trim()}
      >
        <SendHorizonal className="h-4 w-4" />
      </Button>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/ChatInput.tsx
git commit -m "feat: ChatInput component with auto-resize and Enter to send"
```

---

### Task 8: ConnectionStatus Component

**Files:**
- Create: `frontend/src/components/ConnectionStatus.tsx`

**Step 1: Implement ConnectionStatus**

`frontend/src/components/ConnectionStatus.tsx`:
```typescript
import { Badge } from "@/components/ui/badge"
import type { ConnectionStatus as Status } from "@/types"

const statusConfig: Record<Status, { label: string; variant: "success" | "destructive" | "warning" }> = {
  connected: { label: "연결됨", variant: "success" },
  disconnected: { label: "연결 끊김", variant: "destructive" },
  reconnecting: { label: "재연결 중...", variant: "warning" },
}

interface ConnectionStatusProps {
  status: Status
}

export function ConnectionStatus({ status }: ConnectionStatusProps) {
  const config = statusConfig[status]
  return (
    <Badge variant={config.variant} className="text-xs">
      <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${
        status === "connected" ? "bg-green-400" :
        status === "reconnecting" ? "bg-yellow-400 animate-pulse" :
        "bg-red-400"
      }`} />
      {config.label}
    </Badge>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/ConnectionStatus.tsx
git commit -m "feat: ConnectionStatus badge component"
```

---

### Task 9: ChatContainer Component

**Files:**
- Create: `frontend/src/components/ChatContainer.tsx`

**Step 1: Implement ChatContainer with auto-scroll**

`frontend/src/components/ChatContainer.tsx`:
```typescript
import { useEffect, useRef } from "react"
import { ChatMessage } from "@/components/ChatMessage"
import { ApprovalCard } from "@/components/ApprovalCard"
import { Loader2 } from "lucide-react"
import type { Message } from "@/types"

interface ChatContainerProps {
  messages: Message[]
  isWaitingResponse: boolean
  onApprove: () => void
  onReject: () => void
}

export function ChatContainer({ messages, isWaitingResponse, onApprove, onReject }: ChatContainerProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isWaitingResponse])

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4">
      {messages.length === 0 && (
        <div className="flex h-full items-center justify-center text-muted-foreground">
          <p className="text-center text-sm">
            GP Claw에 오신 것을 환영합니다.<br />
            메시지를 입력해서 시작하세요.
          </p>
        </div>
      )}

      {messages.map((msg) => {
        if (msg.type === "approval_request") {
          return (
            <ApprovalCard
              key={msg.id}
              message={msg}
              onApprove={onApprove}
              onReject={onReject}
            />
          )
        }
        return <ChatMessage key={msg.id} message={msg} />
      })}

      {isWaitingResponse && (
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          <span className="text-sm">응답 생성 중...</span>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/ChatContainer.tsx
git commit -m "feat: ChatContainer with auto-scroll and loading indicator"
```

---

### Task 10: App.tsx — Wire Everything Together

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/index.css` (add html dark class)
- Modify: `frontend/index.html` (add dark class to html tag)

**Step 1: Add dark class to HTML**

`frontend/index.html` — add `class="dark"` to `<html>` tag:
```html
<html lang="ko" class="dark">
```

**Step 2: Update App.tsx**

`frontend/src/App.tsx`:
```typescript
import { ChatContainer } from "@/components/ChatContainer"
import { ChatInput } from "@/components/ChatInput"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { useWebSocket } from "@/hooks/useWebSocket"
import { Cog } from "lucide-react"

function App() {
  const {
    messages,
    connectionStatus,
    isWaitingResponse,
    isWaitingApproval,
    sendMessage,
    sendApproval,
  } = useWebSocket()

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Cog className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-semibold text-foreground">GP Claw</h1>
        </div>
        <ConnectionStatus status={connectionStatus} />
      </header>

      {/* Chat */}
      <ChatContainer
        messages={messages}
        isWaitingResponse={isWaitingResponse}
        onApprove={() => sendApproval("approved")}
        onReject={() => sendApproval("rejected")}
      />

      {/* Input */}
      <ChatInput
        onSend={sendMessage}
        disabled={isWaitingResponse || isWaitingApproval || connectionStatus !== "connected"}
      />
    </div>
  )
}

export default App
```

**Step 3: Clean up main.tsx**

`frontend/src/main.tsx`:
```typescript
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import "./index.css"
import App from "./App"

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
)
```

**Step 4: Verify build**

```bash
cd frontend && npm run build
```

**Step 5: Commit**

```bash
git add frontend/
git commit -m "feat: wire up App.tsx with all components and WebSocket hook"
```

---

### Task 11: Manual E2E Verification

**Step 1: Start backend**

```bash
cd /Users/goldenplanet/jinsup_space/gp_claw
source .venv/bin/activate
python -m gp_claw
```

**Step 2: Start frontend dev server**

```bash
cd frontend
npm run dev
```

**Step 3: Verify in browser**

1. http://localhost:5173 접속
2. 연결 상태 "연결됨" 확인
3. 메시지 전송 → 에코 응답 확인 (LLM 없이)
4. WebSocket 연결 끊김 → 재연결 확인

**Step 4: Final commit (if any fixes needed)**

```bash
git add frontend/
git commit -m "fix: adjustments from E2E verification"
```
