import { useCallback, useEffect, useRef, useState } from "react"
import type { ConnectionStatus, Message, WsReceive, WsSend } from "@/types"

interface UseWebSocketReturn {
  messages: Message[]
  connectionStatus: ConnectionStatus
  isWaitingResponse: boolean
  isWaitingApproval: boolean
  currentWorkspace: string | null
  sendMessage: (content: string) => void
  sendApproval: (decision: "approved" | "rejected") => void
  setWorkspace: (path: string) => void
  openFile: (path: string) => void
}

export function useWebSocket(
  roomId: string | null,
  onRoomTitleUpdate?: (roomId: string, title: string) => void,
): UseWebSocketReturn {
  const [messages, setMessages] = useState<Message[]>([])
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("disconnected")
  const [isWaitingResponse, setIsWaitingResponse] = useState(false)
  const [isWaitingApproval, setIsWaitingApproval] = useState(false)
  const [currentWorkspace, setCurrentWorkspace] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)
  const roomIdRef = useRef(roomId)
  const onRoomTitleUpdateRef = useRef(onRoomTitleUpdate)

  // Keep refs in sync
  roomIdRef.current = roomId
  onRoomTitleUpdateRef.current = onRoomTitleUpdate

  const send = useCallback((data: WsSend) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  const handleMessage = useCallback((event: MessageEvent) => {
    const data: WsReceive = JSON.parse(event.data)

    switch (data.type) {
      case "assistant_chunk":
        setMessages((prev) => {
          const last = prev[prev.length - 1]
          if (last?.type === "assistant") {
            return [
              ...prev.slice(0, -1),
              { ...last, content: last.content + data.content },
            ]
          }
          return [
            ...prev,
            { id: crypto.randomUUID(), type: "assistant", content: data.content, timestamp: Date.now() },
          ]
        })
        break

      case "assistant_done":
        setIsWaitingResponse(false)
        setIsWaitingApproval(false)
        break

      case "assistant_message":
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), type: "assistant", content: data.content, timestamp: Date.now() },
        ])
        setIsWaitingResponse(false)
        setIsWaitingApproval(false)
        break

      case "approval_request":
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            type: "approval_request",
            toolCalls: data.tool_calls,
            status: "pending",
            timestamp: Date.now(),
          },
        ])
        setIsWaitingResponse(false)
        setIsWaitingApproval(true)
        break

      case "error":
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), type: "error", content: data.content, timestamp: Date.now() },
        ])
        setIsWaitingResponse(false)
        setIsWaitingApproval(false)
        break

      case "workspace_changed":
        setCurrentWorkspace(data.display)
        break

      case "workspace_error":
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), type: "error", content: data.content, timestamp: Date.now() },
        ])
        break

      case "file_opened":
        break

      case "file_created":
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            type: "file_card",
            filename: data.filename,
            path: data.path,
            sizeBytes: data.size_bytes,
            timestamp: Date.now(),
          },
        ])
        break

      case "room_title_updated":
        onRoomTitleUpdateRef.current?.(data.room_id, data.title)
        break

      case "pong":
        break
    }
  }, [])

  const cleanup = useCallback(() => {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
    if (pingTimerRef.current) clearInterval(pingTimerRef.current)
    reconnectTimerRef.current = undefined
    pingTimerRef.current = undefined
    if (wsRef.current) {
      wsRef.current.onclose = null // prevent reconnect
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  const connect = useCallback((rid: string) => {
    cleanup()

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
    const wsUrl = `${protocol}//${window.location.host}/ws/${rid}`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnectionStatus("connected")
      reconnectAttemptRef.current = 0

      pingTimerRef.current = setInterval(() => {
        send({ type: "ping" })
      }, 30_000)
    }

    ws.onmessage = handleMessage

    ws.onclose = () => {
      setConnectionStatus("disconnected")
      if (pingTimerRef.current) clearInterval(pingTimerRef.current)

      // roomId가 여전히 같을 때만 재연결
      if (roomIdRef.current === rid) {
        const delay = Math.min(1000 * 2 ** reconnectAttemptRef.current, 30_000)
        reconnectAttemptRef.current += 1
        setConnectionStatus("reconnecting")
        reconnectTimerRef.current = setTimeout(() => connect(rid), delay)
      }
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [cleanup, handleMessage, send])

  // roomId 변경 시: 히스토리 로드 + WS 재연결
  useEffect(() => {
    if (!roomId) {
      cleanup()
      setMessages([])
      setConnectionStatus("disconnected")
      setIsWaitingResponse(false)
      setIsWaitingApproval(false)
      return
    }

    let cancelled = false

    ;(async () => {
      // 히스토리 로드
      try {
        const res = await fetch(`/rooms/${roomId}/messages`)
        if (cancelled) return
        if (res.ok) {
          const history: { id: number; type: string; content: string; created_at: string }[] = await res.json()
          const restored: Message[] = history
            .filter((m) => m.type === "user" || m.type === "assistant")
            .map((m) => ({
              id: crypto.randomUUID(),
              type: m.type as "user" | "assistant",
              content: m.content,
              timestamp: new Date(m.created_at).getTime(),
              serverMessageId: m.id,
            }))
          setMessages(restored)
        } else {
          setMessages([])
        }
      } catch {
        if (!cancelled) setMessages([])
      }

      if (!cancelled) {
        reconnectAttemptRef.current = 0
        connect(roomId)
      }
    })()

    return () => {
      cancelled = true
      cleanup()
    }
  }, [roomId, connect, cleanup])

  const sendMessage = useCallback(
    (content: string) => {
      if (!content.trim()) return
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), type: "user", content, timestamp: Date.now() },
      ])
      setIsWaitingResponse(true)
      send({ type: "user_message", content })
    },
    [send]
  )

  const sendApproval = useCallback(
    (decision: "approved" | "rejected") => {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.type === "approval_request" && msg.status === "pending"
            ? { ...msg, status: decision }
            : msg
        )
      )
      setIsWaitingApproval(false)
      setIsWaitingResponse(true)
      send({ type: "approval_response", decision })
    },
    [send]
  )

  const setWorkspace = useCallback(
    (path: string) => {
      send({ type: "set_workspace", path })
    },
    [send]
  )

  const openFile = useCallback(
    (path: string) => {
      send({ type: "open_file", path })
    },
    [send]
  )

  return {
    messages,
    connectionStatus,
    isWaitingResponse,
    isWaitingApproval,
    currentWorkspace,
    sendMessage,
    sendApproval,
    setWorkspace,
    openFile,
  }
}
