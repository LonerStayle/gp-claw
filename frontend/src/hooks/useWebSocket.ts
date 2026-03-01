import { useCallback, useEffect, useRef, useState } from "react"
import type { ConnectionStatus, Message, WsReceive, WsSend } from "@/types"

function generateSessionId(): string {
  const stored = sessionStorage.getItem("gp-claw-session-id")
  if (stored) return stored
  const id = crypto.randomUUID()
  sessionStorage.setItem("gp-claw-session-id", id)
  return id
}

interface UseWebSocketReturn {
  messages: Message[]
  connectionStatus: ConnectionStatus
  isWaitingResponse: boolean
  isWaitingApproval: boolean
  currentWorkspace: string | null
  sendMessage: (content: string) => void
  sendApproval: (decision: "approved" | "rejected") => void
  setWorkspace: (path: string) => void
}

export function useWebSocket(): UseWebSocketReturn {
  const [messages, setMessages] = useState<Message[]>([])
  const [connectionStatus, setConnectionStatus] = useState<ConnectionStatus>("disconnected")
  const [isWaitingResponse, setIsWaitingResponse] = useState(false)
  const [isWaitingApproval, setIsWaitingApproval] = useState(false)
  const [currentWorkspace, setCurrentWorkspace] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptRef = useRef(0)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const pingTimerRef = useRef<ReturnType<typeof setInterval> | undefined>(undefined)

  const send = useCallback((data: WsSend) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data))
    }
  }, [])

  const handleMessage = useCallback((event: MessageEvent) => {
    const data: WsReceive = JSON.parse(event.data)

    switch (data.type) {
      case "assistant_message":
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), type: "assistant", content: data.content },
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
          },
        ])
        setIsWaitingResponse(false)
        setIsWaitingApproval(true)
        break

      case "error":
        setMessages((prev) => [
          ...prev,
          { id: crypto.randomUUID(), type: "error", content: data.content },
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
          { id: crypto.randomUUID(), type: "error", content: data.content },
        ])
        break

      case "pong":
        break
    }
  }, [])

  const connect = useCallback(() => {
    const sessionId = generateSessionId()
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:"
    const wsUrl = `${protocol}//${window.location.host}/ws/${sessionId}`

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

      const delay = Math.min(1000 * 2 ** reconnectAttemptRef.current, 30_000)
      reconnectAttemptRef.current += 1
      setConnectionStatus("reconnecting")
      reconnectTimerRef.current = setTimeout(connect, delay)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [handleMessage, send])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current)
      if (pingTimerRef.current) clearInterval(pingTimerRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  const sendMessage = useCallback(
    (content: string) => {
      if (!content.trim()) return
      setMessages((prev) => [
        ...prev,
        { id: crypto.randomUUID(), type: "user", content },
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

  return {
    messages,
    connectionStatus,
    isWaitingResponse,
    isWaitingApproval,
    currentWorkspace,
    sendMessage,
    sendApproval,
    setWorkspace,
  }
}
