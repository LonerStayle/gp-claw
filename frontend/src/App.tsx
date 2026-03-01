import { ChatContainer } from "@/components/ChatContainer"
import { ChatInput } from "@/components/ChatInput"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { FolderPicker } from "@/components/FolderPicker"
import { useWebSocket } from "@/hooks/useWebSocket"
import { Cog } from "lucide-react"

function App() {
  const {
    messages,
    connectionStatus,
    isWaitingResponse,
    isWaitingApproval,
    currentWorkspace,
    sendMessage,
    sendApproval,
    setWorkspace,
  } = useWebSocket()

  return (
    <div className="flex h-screen flex-col bg-background">
      {/* Header */}
      <header className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <Cog className="h-5 w-5 text-primary" />
          <h1 className="text-lg font-semibold text-foreground">GP Claw</h1>
          <span className="text-border">|</span>
          <FolderPicker currentWorkspace={currentWorkspace} onSetWorkspace={setWorkspace} />
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
