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
