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
  | { type: "set_workspace"; path: string }
  | { type: "ping" }

export type WsReceive =
  | { type: "assistant_message"; content: string }
  | { type: "approval_request"; tool_calls: ToolCall[] }
  | { type: "error"; content: string }
  | { type: "workspace_changed"; path: string; display: string }
  | { type: "workspace_error"; content: string }
  | { type: "pong" }

// --- Connection status ---
export type ConnectionStatus = "connected" | "disconnected" | "reconnecting"
