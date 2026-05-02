import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

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
          <p className="whitespace-pre-wrap break-words">{renderHighlighted(message.content, highlightQuery)}</p>
        )}
      </div>
      <span className="mt-1 text-[10px] text-muted-foreground/60 px-1">
        {formatTime(message.timestamp)}
      </span>
    </div>
  )
}
