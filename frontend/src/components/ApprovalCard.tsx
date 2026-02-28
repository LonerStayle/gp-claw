import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import type { ApprovalRequestMessage } from "@/types"
import { ShieldAlert, Check, X } from "lucide-react"

interface ApprovalCardProps {
  message: ApprovalRequestMessage
  onApprove: () => void
  onReject: () => void
}

export function ApprovalCard({ message, onApprove, onReject }: ApprovalCardProps) {
  const isPending = message.status === "pending"

  return (
    <div className="flex w-full justify-start">
      <Card className="w-full max-w-[90%] border-[hsl(var(--warning))]/30 bg-[hsl(var(--warning))]/5">
        <CardHeader className="pb-2">
          <CardTitle className="flex items-center gap-2 text-[hsl(var(--warning))]">
            <ShieldAlert className="h-4 w-4" />
            승인 필요
            {!isPending && (
              <Badge variant={message.status === "approved" ? "success" : "destructive"}>
                {message.status === "approved" ? "승인됨" : "거부됨"}
              </Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {message.toolCalls.map((tc, i) => (
            <div key={i} className="space-y-1">
              <Badge variant="outline" className="font-mono text-xs">
                {tc.tool}
              </Badge>
              <pre className="mt-1 rounded-md bg-black/30 p-3 text-xs text-muted-foreground overflow-x-auto whitespace-pre-wrap">
                {tc.preview}
              </pre>
            </div>
          ))}
        </CardContent>
        {isPending && (
          <CardFooter className="gap-2">
            <Button size="sm" onClick={onApprove} className="bg-green-600 hover:bg-green-700 text-white">
              <Check className="mr-1 h-3 w-3" />
              승인
            </Button>
            <Button size="sm" variant="destructive" onClick={onReject}>
              <X className="mr-1 h-3 w-3" />
              거부
            </Button>
          </CardFooter>
        )}
      </Card>
    </div>
  )
}
