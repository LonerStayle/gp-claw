import { useState } from "react"
import { FolderOpen, Home, FileText, Download, Monitor } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog"

interface FolderPickerProps {
  currentWorkspace: string | null
  onSetWorkspace: (path: string) => void
}

const QUICK_FOLDERS = [
  { label: "Desktop", path: "~/Desktop", icon: Monitor },
  { label: "Documents", path: "~/Documents", icon: FileText },
  { label: "Downloads", path: "~/Downloads", icon: Download },
  { label: "Home", path: "~", icon: Home },
]

export function FolderPicker({ currentWorkspace, onSetWorkspace }: FolderPickerProps) {
  const [open, setOpen] = useState(false)
  const [inputPath, setInputPath] = useState("")

  const handleApply = () => {
    const path = inputPath.trim()
    if (!path) return
    onSetWorkspace(path)
    setOpen(false)
    setInputPath("")
  }

  const handleQuickSelect = (path: string) => {
    onSetWorkspace(path)
    setOpen(false)
    setInputPath("")
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault()
      handleApply()
    }
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button className="flex items-center gap-1.5 rounded-md px-2 py-1 text-sm text-muted-foreground hover:bg-accent hover:text-foreground transition-colors">
          <FolderOpen className="h-4 w-4" />
          <span className="max-w-[200px] truncate">
            {currentWorkspace ?? "~/.gp_claw/workspace"}
          </span>
        </button>
      </DialogTrigger>

      <DialogContent>
        <DialogHeader>
          <DialogTitle>작업 폴더 설정</DialogTitle>
          <DialogDescription>
            AI가 작업할 폴더를 선택하세요. 선택한 폴더 안에서만 파일을 읽고 쓸 수 있습니다.
          </DialogDescription>
        </DialogHeader>

        {/* Quick folders */}
        <div className="grid grid-cols-2 gap-2">
          {QUICK_FOLDERS.map(({ label, path, icon: Icon }) => (
            <button
              key={path}
              onClick={() => handleQuickSelect(path)}
              className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-foreground hover:bg-accent transition-colors"
            >
              <Icon className="h-4 w-4 text-muted-foreground" />
              {label}
            </button>
          ))}
        </div>

        {/* Manual input */}
        <div className="flex gap-2">
          <input
            type="text"
            value={inputPath}
            onChange={(e) => setInputPath(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="경로 입력 (예: ~/Projects/my-app)"
            className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          />
          <Button onClick={handleApply} disabled={!inputPath.trim()} size="sm">
            설정
          </Button>
        </div>

        {/* Current workspace */}
        {currentWorkspace && (
          <p className="text-xs text-muted-foreground">
            현재: {currentWorkspace}
          </p>
        )}
      </DialogContent>
    </Dialog>
  )
}
