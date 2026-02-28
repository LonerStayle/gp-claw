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
