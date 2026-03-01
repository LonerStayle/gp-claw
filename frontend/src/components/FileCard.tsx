import { Card, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { FileSpreadsheet, FileText, File, Presentation, FolderOpen } from "lucide-react"
import type { FileCardMessage } from "@/types"

interface FileCardProps {
  message: FileCardMessage
  onOpen: (path: string) => void
}

function getFileIcon(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase()
  switch (ext) {
    case "xlsx": case "xls": case "csv":
      return <FileSpreadsheet className="h-5 w-5 text-green-400" />
    case "pdf":
      return <FileText className="h-5 w-5 text-red-400" />
    case "pptx": case "ppt":
      return <Presentation className="h-5 w-5 text-orange-400" />
    default:
      return <File className="h-5 w-5 text-blue-400" />
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function FileCard({ message, onOpen }: FileCardProps) {
  return (
    <div className="flex w-full justify-start">
      <Card className="max-w-[80%] border-border/50 bg-secondary/50">
        <CardContent className="flex items-center gap-3 p-3">
          {getFileIcon(message.filename)}
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium truncate">{message.filename}</p>
            <p className="text-xs text-muted-foreground">{formatSize(message.sizeBytes)}</p>
          </div>
          <Button
            size="sm"
            variant="outline"
            className="shrink-0"
            onClick={() => onOpen(message.path)}
          >
            <FolderOpen className="mr-1 h-3 w-3" />
            열기
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
