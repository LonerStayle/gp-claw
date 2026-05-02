import { useEffect, useRef } from "react"
import { ChatMessage } from "@/components/ChatMessage"
import { ApprovalCard } from "@/components/ApprovalCard"
import { FileCard } from "@/components/FileCard"
import { Loader2 } from "lucide-react"
import type { Message } from "@/types"

interface ChatContainerProps {
  messages: Message[]
  isWaitingResponse: boolean
  onApprove: () => void
  onReject: () => void
  onOpenFile: (path: string) => void
  pendingScroll?: { messageId: number; query: string } | null
  onScrolled?: () => void
}

export function ChatContainer({
  messages,
  isWaitingResponse,
  onApprove,
  onReject,
  onOpenFile,
  pendingScroll,
  onScrolled,
}: ChatContainerProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const messageRefs = useRef<Map<number, HTMLDivElement>>(new Map())

  useEffect(() => {
    if (pendingScroll) return
    bottomRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, isWaitingResponse, pendingScroll])

  useEffect(() => {
    if (!pendingScroll) return
    const el = messageRefs.current.get(pendingScroll.messageId)
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" })
      el.classList.add("ring-2", "ring-yellow-400")
      setTimeout(() => el.classList.remove("ring-2", "ring-yellow-400"), 2500)
      onScrolled?.()
    }
  }, [pendingScroll, messages, onScrolled])

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
        const serverMessageId =
          msg.type === "user" || msg.type === "assistant" ? msg.serverMessageId : undefined
        const setRef = (el: HTMLDivElement | null) => {
          if (serverMessageId == null) return
          if (el) messageRefs.current.set(serverMessageId, el)
          else messageRefs.current.delete(serverMessageId)
        }
        let inner: React.ReactNode
        if (msg.type === "approval_request") {
          inner = (
            <ApprovalCard
              message={msg}
              onApprove={onApprove}
              onReject={onReject}
            />
          )
        } else if (msg.type === "file_card") {
          inner = <FileCard message={msg} onOpen={onOpenFile} />
        } else {
          inner = (
            <ChatMessage
              message={msg}
              highlightQuery={
                pendingScroll && serverMessageId === pendingScroll.messageId
                  ? pendingScroll.query
                  : undefined
              }
            />
          )
        }
        return (
          <div
            key={msg.id}
            ref={setRef}
            data-msg-id={serverMessageId ?? ""}
            className="rounded-md transition-all"
          >
            {inner}
          </div>
        )
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
