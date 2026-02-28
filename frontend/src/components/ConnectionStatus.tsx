import { Badge } from "@/components/ui/badge"
import type { ConnectionStatus as Status } from "@/types"

const statusConfig: Record<Status, { label: string; variant: "success" | "destructive" | "warning" }> = {
  connected: { label: "연결됨", variant: "success" },
  disconnected: { label: "연결 끊김", variant: "destructive" },
  reconnecting: { label: "재연결 중...", variant: "warning" },
}

interface ConnectionStatusProps {
  status: Status
}

export function ConnectionStatus({ status }: ConnectionStatusProps) {
  const config = statusConfig[status]
  return (
    <Badge variant={config.variant} className="text-xs">
      <span className={`mr-1.5 inline-block h-1.5 w-1.5 rounded-full ${
        status === "connected" ? "bg-green-400" :
        status === "reconnecting" ? "bg-yellow-400 animate-pulse" :
        "bg-red-400"
      }`} />
      {config.label}
    </Badge>
  )
}
