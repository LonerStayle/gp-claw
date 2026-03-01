import { useCallback, useEffect, useState } from "react"
import type { Room } from "@/types"

interface UseRoomsReturn {
  rooms: Room[]
  activeRoomId: string | null
  isLoading: boolean
  createRoom: () => Promise<Room>
  selectRoom: (roomId: string) => void
  renameRoom: (roomId: string, title: string) => Promise<void>
  deleteRoom: (roomId: string) => Promise<void>
  updateRoomInList: (roomId: string, updates: Partial<Room>) => void
}

export function useRooms(): UseRoomsReturn {
  const [rooms, setRooms] = useState<Room[]>([])
  const [activeRoomId, setActiveRoomId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  // 방 목록 로드
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch("/rooms")
        const data: Room[] = await res.json()
        if (cancelled) return

        setRooms(data)
        if (data.length > 0) {
          setActiveRoomId(data[0].id) // 최신 방 선택
        } else {
          // 방이 없으면 자동 생성
          const res2 = await fetch("/rooms", { method: "POST" })
          const newRoom: Room = await res2.json()
          if (cancelled) return
          setRooms([newRoom])
          setActiveRoomId(newRoom.id)
        }
      } catch {
        // 네트워크 오류 시 무시
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [])

  const createRoom = useCallback(async (): Promise<Room> => {
    const res = await fetch("/rooms", { method: "POST" })
    const room: Room = await res.json()
    setRooms((prev) => [room, ...prev])
    setActiveRoomId(room.id)
    return room
  }, [])

  const selectRoom = useCallback((roomId: string) => {
    setActiveRoomId(roomId)
  }, [])

  const renameRoom = useCallback(async (roomId: string, title: string) => {
    await fetch(`/rooms/${roomId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    })
    setRooms((prev) =>
      prev.map((r) => (r.id === roomId ? { ...r, title } : r))
    )
  }, [])

  const deleteRoom = useCallback(async (roomId: string) => {
    await fetch(`/rooms/${roomId}`, { method: "DELETE" })
    setRooms((prev) => {
      const next = prev.filter((r) => r.id !== roomId)
      // 삭제된 방이 활성 방이면 다음 방 선택
      setActiveRoomId((current) => {
        if (current === roomId) {
          return next.length > 0 ? next[0].id : null
        }
        return current
      })
      return next
    })
  }, [])

  const updateRoomInList = useCallback((roomId: string, updates: Partial<Room>) => {
    setRooms((prev) =>
      prev.map((r) => (r.id === roomId ? { ...r, ...updates } : r))
    )
  }, [])

  return {
    rooms,
    activeRoomId,
    isLoading,
    createRoom,
    selectRoom,
    renameRoom,
    deleteRoom,
    updateRoomInList,
  }
}
