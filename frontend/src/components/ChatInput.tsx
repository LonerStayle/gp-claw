import { useState, useRef, useCallback, useEffect } from "react"
import { Button } from "@/components/ui/button"
import { AlertTriangle, Loader2, Paperclip, SendHorizonal, X } from "lucide-react"
import {
  ALLOWED_EXTENSIONS,
  MAX_FILE_SIZE,
  preflightCheck,
  uploadFile,
  UploadError,
} from "@/lib/uploadFile"
import { cn } from "@/lib/utils"
import type { FileAttachment } from "@/types"

interface ChatInputProps {
  onSend: (content: string, attachments?: FileAttachment[]) => void
  disabled: boolean
  /** 활성 room id — 첨부 업로드 시 필요. null 이면 첨부 비활성화. */
  roomId: string | null
}

/** 업로드 진행 중인 파일의 UI 상태.
 * spec: chip 상태 5종
 *  - uploading (0~99% 진행률)
 *  - summarizing (LLM 요약 중)
 *  - done (경로 chip + 본문 반영 완료)
 *  - degraded (경고 아이콘, 일부만 반영)
 *  - error (빨간 배지)
 */
export type ChipStatus =
  | "uploading"
  | "summarizing"
  | "done"
  | "degraded"
  | "error"

interface PendingUpload {
  id: string
  filename: string
  size: number
  progress: number // 0..1
  status: ChipStatus
  errorMsg?: string
  /** 업로드 성공 시 서버 응답 — 메시지 전송 시 사용. */
  attachment?: FileAttachment
}

/** 서버 응답으로부터 chip 상태 결정. */
export function deriveChipStatus(att: FileAttachment): ChipStatus {
  if (att.extraction === "summarizing") return "summarizing"
  if (att.extraction === "error") return "error"
  if (att.degraded || att.extraction_mode === "truncated") return "degraded"
  return "done"
}

const ACCEPT_ATTR = ALLOWED_EXTENSIONS.join(",")

export function ChatInput({ onSend, disabled, roomId }: ChatInputProps) {
  const [input, setInput] = useState("")
  const [pending, setPending] = useState<PendingUpload[]>([])
  const [isDragOver, setIsDragOver] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const dragCounter = useRef(0)

  // feedback 자동 소거
  useEffect(() => {
    if (!feedback) return
    const t = setTimeout(() => setFeedback(null), 4000)
    return () => clearTimeout(t)
  }, [feedback])

  // 'done' 또는 'degraded' 첨부는 메시지에 포함 (degraded도 일부 본문 있음)
  const completedAttachments = pending
    .filter(
      (p) => (p.status === "done" || p.status === "degraded") && p.attachment,
    )
    .map((p) => p.attachment as FileAttachment)
  const hasUploading = pending.some(
    (p) => p.status === "uploading" || p.status === "summarizing",
  )
  const hasAttachments = completedAttachments.length > 0
  const canSend =
    !disabled && !hasUploading && (input.trim().length > 0 || hasAttachments)

  const handleSend = useCallback(() => {
    if (!canSend) return
    onSend(input.trim(), hasAttachments ? completedAttachments : undefined)
    setInput("")
    setPending([])
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto"
    }
  }, [canSend, completedAttachments, hasAttachments, input, onSend])

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value)
    const el = e.target
    el.style.height = "auto"
    el.style.height = Math.min(el.scrollHeight, 200) + "px"
  }

  const beginUpload = useCallback(
    async (file: File) => {
      if (!roomId) {
        setFeedback("대화방이 선택되지 않아 첨부할 수 없습니다")
        return
      }
      // 클라이언트 사전 검증 (즉시 사용자 피드백)
      const pre = preflightCheck(file)
      if (pre) {
        setFeedback(pre.message)
        return
      }

      const id = crypto.randomUUID()
      setPending((prev) => [
        ...prev,
        {
          id,
          filename: file.name,
          size: file.size,
          progress: 0,
          status: "uploading",
        },
      ])

      try {
        const res = await uploadFile(roomId, file, (loaded, total) => {
          setPending((prev) =>
            prev.map((p) =>
              p.id === id ? { ...p, progress: total > 0 ? loaded / total : 0 } : p,
            ),
          )
        })
        // 추출 상태 기반 chip 결정
        const chipStatus = deriveChipStatus(res)
        const errorMsg =
          chipStatus === "error"
            ? res.extraction_error ?? "본문 추출 실패"
            : chipStatus === "degraded"
              ? "본문 일부만 반영됨 (요약 실패 → 잘린 원문)"
              : undefined
        setPending((prev) =>
          prev.map((p) =>
            p.id === id
              ? {
                  ...p,
                  progress: 1,
                  status: chipStatus,
                  attachment: res,
                  filename: res.filename,
                  errorMsg,
                }
              : p,
          ),
        )
      } catch (err) {
        const msg =
          err instanceof UploadError
            ? err.message
            : "업로드 중 오류가 발생했습니다"
        setPending((prev) =>
          prev.map((p) =>
            p.id === id ? { ...p, status: "error", errorMsg: msg } : p,
          ),
        )
        setFeedback(msg)
      }
    },
    [roomId],
  )

  const handleFiles = useCallback(
    (files: FileList | File[] | null) => {
      if (!files) return
      Array.from(files).forEach(beginUpload)
    },
    [beginUpload],
  )

  const handleFileInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files)
    // 같은 파일 재선택 가능하도록 input 리셋
    e.target.value = ""
  }

  // --- Drag & drop ---
  const onDragEnter = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!roomId || disabled) return
    dragCounter.current += 1
    setIsDragOver(true)
  }
  const onDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current -= 1
    if (dragCounter.current <= 0) {
      dragCounter.current = 0
      setIsDragOver(false)
    }
  }
  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragCounter.current = 0
    setIsDragOver(false)
    if (!roomId || disabled) return
    handleFiles(e.dataTransfer.files)
  }

  const removePending = (id: string) => {
    setPending((prev) => prev.filter((p) => p.id !== id))
  }

  return (
    <div
      className={cn(
        "border-t border-border bg-background p-4 transition-colors",
        isDragOver && "bg-primary/5 ring-2 ring-primary/40 ring-inset",
      )}
      onDragEnter={onDragEnter}
      onDragLeave={onDragLeave}
      onDragOver={onDragOver}
      onDrop={onDrop}
    >
      {/* Pending uploads / attached chips */}
      {pending.length > 0 && (
        <ul className="mb-2 flex flex-wrap gap-2" data-testid="pending-uploads">
          {pending.map((p) => (
            <li
              key={p.id}
              data-testid={`chip-${p.status}`}
              data-chip-status={p.status}
              className={cn(
                "flex items-center gap-2 rounded-md border px-2 py-1 text-xs",
                p.status === "done" &&
                  "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
                p.status === "uploading" &&
                  "border-border bg-secondary text-foreground/80",
                p.status === "summarizing" &&
                  "border-blue-500/40 bg-blue-500/10 text-blue-300",
                p.status === "degraded" &&
                  "border-amber-500/40 bg-amber-500/10 text-amber-300",
                p.status === "error" &&
                  "border-destructive/50 bg-destructive/10 text-red-300",
              )}
              title={
                p.status === "degraded"
                  ? "일부만 반영됨 — 요약 실패로 앞부분만 LLM에 전달됨"
                  : p.attachment?.path ?? p.filename
              }
            >
              {p.status === "uploading" ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : p.status === "summarizing" ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : p.status === "error" ? (
                <X className="h-3 w-3" />
              ) : p.status === "degraded" ? (
                <AlertTriangle className="h-3 w-3" />
              ) : (
                <Paperclip className="h-3 w-3" />
              )}
              <span className="max-w-[18rem] truncate font-mono">
                {p.attachment?.path ?? p.filename}
              </span>
              {p.status === "uploading" && (
                <span className="tabular-nums text-muted-foreground">
                  {Math.round(p.progress * 100)}%
                </span>
              )}
              {p.status === "summarizing" && (
                <span className="text-blue-300">— 요약 중</span>
              )}
              {p.status === "degraded" && (
                <span className="text-amber-300">— 일부만 반영</span>
              )}
              {p.status === "error" && p.errorMsg && (
                <span className="text-red-300">— {p.errorMsg}</span>
              )}
              <button
                type="button"
                onClick={() => removePending(p.id)}
                className="rounded p-0.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
                aria-label="remove attachment"
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Inline feedback (validation errors etc.) */}
      {feedback && (
        <div
          role="alert"
          className="mb-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-1.5 text-xs text-red-300"
        >
          {feedback}
        </div>
      )}

      <div className="flex items-end gap-2">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPT_ATTR}
          className="hidden"
          onChange={handleFileInputChange}
          aria-label="파일 선택"
        />
        <Button
          type="button"
          size="icon"
          variant="ghost"
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || !roomId}
          title={`파일 첨부 (${ALLOWED_EXTENSIONS.join(", ")} · ≤${MAX_FILE_SIZE / (1024 * 1024)}MB)`}
        >
          <Paperclip className="h-4 w-4" />
        </Button>

        <textarea
          ref={textareaRef}
          value={input}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={
            isDragOver
              ? "여기에 파일을 놓으세요"
              : disabled
                ? "응답 대기 중..."
                : "메시지를 입력하거나 파일을 드래그&드롭하세요..."
          }
          disabled={disabled}
          rows={1}
          className="flex-1 resize-none rounded-lg border border-input bg-secondary px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
        />
        <Button size="icon" onClick={handleSend} disabled={!canSend}>
          <SendHorizonal className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
