import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Paperclip } from "lucide-react"

import { cn } from "@/lib/utils"
import type { AssistantMessage, ErrorMessage, UserMessage } from "@/types"

interface ChatMessageProps {
  message: UserMessage | AssistantMessage | ErrorMessage
  highlightQuery?: string
}

function formatTime(timestamp: number): string {
  const d = new Date(timestamp)
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })
}

function renderHighlighted(text: string, query: string | undefined) {
  if (!query) return <>{text}</>
  const lower = text.toLowerCase()
  const ql = query.toLowerCase()
  const idx = lower.indexOf(ql)
  if (idx < 0) return <>{text}</>
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-yellow-200">{text.slice(idx, idx + query.length)}</mark>
      {text.slice(idx + query.length)}
    </>
  )
}

export function ChatMessage({ message, highlightQuery }: ChatMessageProps) {
  const isUser = message.type === "user"
  const isError = message.type === "error"
  const isAssistant = message.type === "assistant"
  const attachments = isUser ? (message as UserMessage).attachments : undefined

  return (
    <div className={cn("flex w-full flex-col", isUser ? "items-end" : "items-start")}>
      <div
        className={cn(
          "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
          isUser && "bg-primary text-primary-foreground shadow-md ring-1 ring-primary/20",
          isAssistant && "bg-secondary text-secondary-foreground",
          isError && "bg-destructive/20 text-red-400 border border-destructive/30"
        )}
      >
        {isAssistant ? (
          <div className="markdown-body">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        ) : (
          <>
            {message.content && (
              <p className="whitespace-pre-wrap break-words">{renderHighlighted(message.content, highlightQuery)}</p>
            )}
            {/* 첨부 경로 chip — 메시지 본문에 임베딩 (다운로드 링크가 아닌 경로 문자열) */}
            {attachments && attachments.length > 0 && (
              <ul
                className={cn(
                  "flex flex-wrap gap-1.5",
                  message.content ? "mt-2" : "",
                )}
                data-testid="attachment-chips"
              >
                {attachments.map((a) => {
                  // path: "sandbox/<roomId>/<filename>" → "/api/rooms/<roomId>/files/<filename>"
                  const parts = a.path.split("/")
                  const href =
                    parts.length >= 3 && parts[0] === "sandbox"
                      ? `/api/rooms/${encodeURIComponent(parts[1])}/files/${encodeURIComponent(parts.slice(2).join("/"))}`
                      : `/${a.path}`
                  return (
                    <li key={a.path} className="inline-flex">
                      <a
                        href={href}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 rounded-md bg-primary-foreground/15 px-2 py-0.5 text-[11px] font-mono text-primary-foreground/95 ring-1 ring-primary-foreground/20 hover:bg-primary-foreground/25 hover:underline"
                        title={`${a.path} · ${a.size} bytes · ${a.mime} (클릭하여 새 탭에서 열기)`}
                      >
                        <Paperclip className="h-3 w-3 opacity-80" />
                        <span className="truncate max-w-[16rem]">{a.path}</span>
                      </a>
                    </li>
                  )
                })}
              </ul>
            )}
          </>
        )}
      </div>
      <span className="mt-1 text-[10px] text-muted-foreground/60 px-1">
        {formatTime(message.timestamp)}
      </span>
    </div>
  )
}
