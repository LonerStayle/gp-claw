// --- Room ---
export interface Room {
  id: string
  title: string
  created_at: string
  updated_at: string
}

// --- Tool Call ---
export interface ToolCall {
  tool: string
  args: Record<string, unknown>
  preview: string
}

// --- Attachments ---
export type ExtractionStatus = "ready" | "summarizing" | "error"
export type ExtractionMode = "raw" | "summary" | "truncated" | "error"

export interface FileAttachment {
  /** project-root-relative path returned from upload, e.g. "sandbox/<roomId>/report.pdf" */
  path: string
  /** display filename (basename of path, after server-side sanitize/rename) */
  filename: string
  size: number
  mime: string
  /** 추출 상태 (서버 응답). 동기 처리 → 'ready' | 'error', 비동기 → 'summarizing' */
  extraction?: ExtractionStatus
  /** 추출 모드 — chip 표시에 사용 */
  extraction_mode?: ExtractionMode
  /** 본문 일부만 반영된 경우 true */
  degraded?: boolean
  /** 추출 실패 메시지 */
  extraction_error?: string | null
}

// --- Messages (UI state) ---
export interface UserMessage {
  id: string
  type: "user"
  content: string
  timestamp: number
  serverMessageId?: number  // /rooms/{id}/messages 응답의 id (R-7 / FR-4 점프용)
  attachments?: FileAttachment[]
}

export interface AssistantMessage {
  id: string
  type: "assistant"
  content: string
  timestamp: number
  serverMessageId?: number  // /rooms/{id}/messages 응답의 id (R-7 / FR-4 점프용)
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

export type Message = UserMessage | AssistantMessage | ApprovalRequestMessage | ErrorMessage | FileCardMessage

// --- WebSocket protocol (wire format) ---
export type WsSend =
  | { type: "user_message"; content: string; attachments?: FileAttachment[] }
  | { type: "approval_response"; decision: "approved" | "rejected" }
  | { type: "set_workspace"; path: string }
  | { type: "open_file"; path: string }
  | { type: "ping" }

export type WsReceive =
  | { type: "assistant_message"; content: string }
  | { type: "assistant_chunk"; content: string }
  | { type: "assistant_done" }
  | { type: "approval_request"; tool_calls: ToolCall[] }
  | { type: "error"; content: string }
  | { type: "workspace_changed"; path: string; display: string }
  | { type: "workspace_error"; content: string }
  | { type: "file_opened"; path: string; filename: string }
  | { type: "file_created"; path: string; filename: string; size_bytes: number }
  | { type: "room_title_updated"; room_id: string; title: string }
  | { type: "pong" }

// --- Connection status ---
export type ConnectionStatus = "connected" | "disconnected" | "reconnecting"

// --- Search ---
export type MessageRole = "user" | "assistant" | "tool" | "system"

export interface SearchResultItem {
  id: number
  room_id: string
  room_title: string
  role: MessageRole
  content: string
  snippet: string
  match_offsets: [number, number][]
  created_at: string
}

export interface SearchResponse {
  total: number
  items: SearchResultItem[]
}

export interface SearchFilter {
  q: string
  roomIds: string[]
  roles: MessageRole[]
  dateFrom?: string  // ISO
  dateTo?: string    // ISO
}
