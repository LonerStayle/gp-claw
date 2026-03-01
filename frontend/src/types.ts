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
  timestamp: number
}

export interface AssistantMessage {
  id: string
  type: "assistant"
  content: string
  timestamp: number
}

export interface ApprovalRequestMessage {
  id: string
  type: "approval_request"
  toolCalls: ToolCall[]
  status: "pending" | "approved" | "rejected"
  timestamp: number
}

export interface ErrorMessage {
  id: string
  type: "error"
  content: string
  timestamp: number
}

export interface FileCardMessage {
  id: string
  type: "file_card"
  filename: string
  path: string
  sizeBytes: number
  timestamp: number
}

export interface ThinkingMessage {
  id: string
  type: "thinking"
  content: string
  isComplete: boolean
  timestamp: number
}

export type Message = UserMessage | AssistantMessage | ApprovalRequestMessage | ErrorMessage | FileCardMessage | ThinkingMessage

// --- WebSocket protocol (wire format) ---
export type WsSend =
  | { type: "user_message"; content: string }
  | { type: "approval_response"; decision: "approved" | "rejected" }
  | { type: "set_workspace"; path: string }
  | { type: "open_file"; path: string }
  | { type: "ping" }

export type WsReceive =
  | { type: "assistant_message"; content: string }
  | { type: "assistant_chunk"; content: string }
  | { type: "assistant_done" }
  | { type: "thinking_start" }
  | { type: "thinking_chunk"; content: string }
  | { type: "thinking_done" }
  | { type: "approval_request"; tool_calls: ToolCall[] }
  | { type: "error"; content: string }
  | { type: "workspace_changed"; path: string; display: string }
  | { type: "workspace_error"; content: string }
  | { type: "file_opened"; path: string; filename: string }
  | { type: "file_created"; path: string; filename: string; size_bytes: number }
  | { type: "pong" }

// --- Connection status ---
export type ConnectionStatus = "connected" | "disconnected" | "reconnecting"
