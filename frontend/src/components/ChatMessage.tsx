import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { Paperclip } from "lucide-react"

import { cn } from "@/lib/utils"
import type { AssistantMessage, ErrorMessage, UserMessage } from "@/types"

interface ChatMessageProps {
  message: UserMessage | AssistantMessage | ErrorMessage
}

function formatTime(timestamp: number): string {
  const d = new Date(timestamp)
  return d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })
}

export function ChatMessage({ message }: ChatMessageProps) {
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
              <p className="whitespace-pre-wrap break-words">{message.content}</p>
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
                {attachments.map((a) => (
                  <li
                    key={a.path}
                    className="inline-flex items-center gap-1 rounded-md bg-primary-foreground/15 px-2 py-0.5 text-[11px] font-mono text-primary-foreground/95 ring-1 ring-primary-foreground/20"
                    title={`${a.path} · ${a.size} bytes · ${a.mime}`}
                  >
                    <Paperclip className="h-3 w-3 opacity-80" />
                    <span className="truncate max-w-[16rem]">{a.path}</span>
                  </li>
                ))}
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
