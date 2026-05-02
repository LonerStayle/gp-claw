import { useCallback, useRef, useState } from "react"
import { MessageSquarePlus, Pencil, Trash2, Check, X, Filter } from "lucide-react"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogClose,
} from "@/components/ui/dialog"
import type { Room } from "@/types"

interface SidebarProps {
  rooms: Room[]
  activeRoomId: string | null
  onCreateRoom: () => void
  onSelectRoom: (roomId: string) => void
  onRenameRoom: (roomId: string, title: string) => void
  onDeleteRoom: (roomId: string) => void
}

export function Sidebar({
  rooms,
  activeRoomId,
  onCreateRoom,
  onSelectRoom,
  onRenameRoom,
  onDeleteRoom,
}: SidebarProps) {
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState("")
  const [deleteTarget, setDeleteTarget] = useState<Room | null>(null)
  const [roomFilter, setRoomFilter] = useState("")
  const [filterOpen, setFilterOpen] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const startRename = useCallback((room: Room, e: React.MouseEvent) => {
    e.stopPropagation()
    setEditingId(room.id)
    setEditValue(room.title)
    setTimeout(() => inputRef.current?.focus(), 0)
  }, [])

  const confirmRename = useCallback(() => {
    if (editingId && editValue.trim()) {
      onRenameRoom(editingId, editValue.trim())
    }
    setEditingId(null)
  }, [editingId, editValue, onRenameRoom])

  const cancelRename = useCallback(() => {
    setEditingId(null)
  }, [])

  const requestDelete = useCallback((room: Room, e: React.MouseEvent) => {
    e.stopPropagation()
    setDeleteTarget(room)
  }, [])

  const confirmDelete = useCallback(() => {
    if (deleteTarget) {
      onDeleteRoom(deleteTarget.id)
      setDeleteTarget(null)
    }
  }, [deleteTarget, onDeleteRoom])

  const filtered = rooms.filter((r) =>
    r.title.toLowerCase().includes(roomFilter.toLowerCase()),
  )

  return (
    <aside className="flex w-64 flex-col border-r border-border bg-secondary">
      {/* 새 대화 + 방 이름 필터 토글 */}
      <div className="flex items-center gap-1 p-3">
        <button
          onClick={onCreateRoom}
          className="flex flex-1 items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm text-foreground transition-colors hover:bg-accent"
        >
          <MessageSquarePlus className="h-4 w-4" />
          새 대화
        </button>
        <button
          onClick={() => {
            setFilterOpen((v) => {
              if (v) setRoomFilter("")
              return !v
            })
          }}
          className={`rounded-lg border border-border p-2 transition-colors hover:bg-accent ${
            filterOpen ? "bg-accent text-accent-foreground" : "bg-background text-muted-foreground"
          }`}
          title={filterOpen ? "필터 닫기" : "방 이름 필터"}
          aria-label={filterOpen ? "방 이름 필터 닫기" : "방 이름 필터 열기"}
        >
          <Filter className="h-4 w-4" />
        </button>
      </div>

      {filterOpen && (
        <div className="border-b border-border px-3 pb-2">
          <input
            type="text"
            value={roomFilter}
            onChange={(e) => setRoomFilter(e.target.value)}
            placeholder="방 이름 검색…"
            className="w-full rounded border border-border bg-background px-2 py-1 text-xs text-foreground"
            aria-label="방 이름 검색"
            autoFocus
          />
        </div>
      )}

      {/* 방 목록 */}
      <nav className="flex-1 overflow-y-auto px-2 pb-2">
        {filtered.map((room) => {
          const isActive = room.id === activeRoomId
          const isEditing = room.id === editingId

          return (
            <div
              key={room.id}
              onClick={() => !isEditing && onSelectRoom(room.id)}
              className={`group relative mb-0.5 flex cursor-pointer items-center rounded-lg px-3 py-2 text-sm transition-colors ${
                isActive
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
              }`}
            >
              {isEditing ? (
                <div className="flex flex-1 items-center gap-1">
                  <input
                    ref={inputRef}
                    value={editValue}
                    onChange={(e) => setEditValue(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") confirmRename()
                      if (e.key === "Escape") cancelRename()
                    }}
                    className="flex-1 rounded border border-border bg-background px-1 py-0.5 text-sm text-foreground outline-none"
                    onClick={(e) => e.stopPropagation()}
                  />
                  <button onClick={confirmRename} className="p-0.5 text-muted-foreground hover:text-foreground">
                    <Check className="h-3.5 w-3.5" />
                  </button>
                  <button onClick={cancelRename} className="p-0.5 text-muted-foreground hover:text-foreground">
                    <X className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : (
                <>
                  <span className="flex-1 truncate">{room.title}</span>
                  <div className="flex shrink-0 items-center gap-0.5 opacity-0 transition-opacity group-hover:opacity-100">
                    <button
                      onClick={(e) => startRename(room, e)}
                      className="rounded p-0.5 text-muted-foreground hover:text-foreground"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={(e) => requestDelete(room, e)}
                      className="rounded p-0.5 text-muted-foreground hover:text-destructive"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </>
              )}
            </div>
          )
        })}
      </nav>

      {/* 삭제 확인 대화상자 */}
      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>대화 삭제</DialogTitle>
            <DialogDescription>
              &ldquo;{deleteTarget?.title}&rdquo; 대화를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2">
            <DialogClose asChild>
              <button className="rounded-lg border border-border px-3 py-1.5 text-sm text-foreground hover:bg-accent">
                취소
              </button>
            </DialogClose>
            <button
              onClick={confirmDelete}
              className="rounded-lg bg-destructive px-3 py-1.5 text-sm text-destructive-foreground hover:bg-destructive/90"
            >
              삭제
            </button>
          </div>
        </DialogContent>
      </Dialog>
    </aside>
  )
}
