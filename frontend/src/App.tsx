import { useCallback, useEffect, useState } from "react"
import { ChatContainer } from "@/components/ChatContainer"
import { ChatInput } from "@/components/ChatInput"
import { ConnectionStatus } from "@/components/ConnectionStatus"
import { FolderPicker } from "@/components/FolderPicker"
import { SearchBar } from "@/components/SearchBar"
import { SearchResults } from "@/components/SearchResults"
import { Sidebar } from "@/components/Sidebar"
import { useRooms } from "@/hooks/useRooms"
import { useSearch } from "@/hooks/useSearch"
import { useWebSocket } from "@/hooks/useWebSocket"
import type { SearchFilter } from "@/types"
import { Cog, PanelLeftClose, PanelLeftOpen } from "lucide-react"

function App() {
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const {
    rooms,
    activeRoomId,
    isLoading,
    createRoom,
    selectRoom,
    renameRoom,
    deleteRoom,
    updateRoomInList,
  } = useRooms()

  const handleRoomTitleUpdate = useCallback(
    (roomId: string, title: string) => {
      updateRoomInList(roomId, { title })
    },
    [updateRoomInList]
  )

  const {
    messages,
    connectionStatus,
    isWaitingResponse,
    isWaitingApproval,
    currentWorkspace,
    sendMessage,
    sendApproval,
    setWorkspace,
    openFile,
  } = useWebSocket(activeRoomId, handleRoomTitleUpdate)

  // 검색 상태
  const [searchFilter, setSearchFilter] = useState<SearchFilter>({
    q: "",
    roomIds: [],
    roles: [],
  })
  const [pendingScroll, setPendingScroll] = useState<{
    messageId: number
    query: string
  } | null>(null)

  const search = useSearch(searchFilter)
  const isSearchMode = searchFilter.q.length > 0

  const handleJump = useCallback(
    (roomId: string, messageId: number, query: string) => {
      selectRoom(roomId)
      setSearchFilter({ q: "", roomIds: [], roles: [] })
      setPendingScroll({ messageId, query })
    },
    [selectRoom]
  )

  const handleScrolled = useCallback(() => setPendingScroll(null), [])

  // 키보드 단축키: Cmd+Shift+O → 새 대화
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === "o") {
        e.preventDefault()
        createRoom()
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [createRoom])

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-background">
        <p className="text-muted-foreground text-sm">로딩 중...</p>
      </div>
    )
  }

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      {sidebarOpen && (
        <Sidebar
          rooms={rooms}
          activeRoomId={activeRoomId}
          onCreateRoom={createRoom}
          onSelectRoom={selectRoom}
          onRenameRoom={renameRoom}
          onDeleteRoom={deleteRoom}
        />
      )}

      {/* Main */}
      <div className="flex flex-1 flex-col">
        {/* Header */}
        <header className="flex items-center justify-between border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSidebarOpen((v) => !v)}
              className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground"
              title={sidebarOpen ? "사이드바 닫기" : "사이드바 열기"}
            >
              {sidebarOpen ? (
                <PanelLeftClose className="h-5 w-5" />
              ) : (
                <PanelLeftOpen className="h-5 w-5" />
              )}
            </button>
            <Cog className="h-5 w-5 text-primary" />
            <h1 className="text-lg font-semibold text-foreground">GP Claw</h1>
            <span className="text-border">|</span>
            <FolderPicker currentWorkspace={currentWorkspace} onSetWorkspace={setWorkspace} />
          </div>
          <ConnectionStatus status={connectionStatus} />
        </header>

        {/* Chat / Search */}
        {activeRoomId ? (
          <>
            <SearchBar
              rooms={rooms}
              filter={searchFilter}
              onChange={setSearchFilter}
              onClear={() => setSearchFilter({ q: "", roomIds: [], roles: [] })}
            />
            {isSearchMode ? (
              <SearchResults
                query={searchFilter.q}
                items={search.data?.items ?? null}
                total={search.data?.total ?? 0}
                loading={search.loading}
                error={search.error}
                canLoadMore={search.canLoadMore}
                onLoadMore={search.loadMore}
                onJump={handleJump}
              />
            ) : (
              <>
                <ChatContainer
                  messages={messages}
                  isWaitingResponse={isWaitingResponse}
                  onApprove={() => sendApproval("approved")}
                  onReject={() => sendApproval("rejected")}
                  onOpenFile={openFile}
                  pendingScroll={pendingScroll}
                  onScrolled={handleScrolled}
                />
                <ChatInput
                  onSend={sendMessage}
                  disabled={isWaitingResponse || isWaitingApproval || connectionStatus !== "connected"}
                />
              </>
            )}
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center text-muted-foreground">
            <p className="text-sm">새 대화를 시작하거나 기존 대화를 선택하세요.</p>
          </div>
        )}
      </div>
    </div>
  )
}

export default App
