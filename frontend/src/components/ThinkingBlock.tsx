import { useState } from "react"
import { ChevronRight, Brain, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"
import type { ThinkingMessage } from "@/types"

interface ThinkingBlockProps {
  message: ThinkingMessage
}

export function ThinkingBlock({ message }: ThinkingBlockProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="flex w-full flex-col items-start">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition-colors py-1"
      >
        {message.isComplete ? (
          <Brain className="h-3.5 w-3.5" />
        ) : (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        )}
        <span>{message.isComplete ? "생각 과정" : "생각 중..."}</span>
        <ChevronRight
          className={cn(
            "h-3 w-3 transition-transform",
            isOpen && "rotate-90"
          )}
        />
      </button>

      {isOpen && (
        <div className="mt-1 w-full max-w-[80%] rounded-lg border border-border/50 bg-muted/30 px-3 py-2 text-xs text-muted-foreground whitespace-pre-wrap leading-relaxed">
          {message.content || "..."}
        </div>
      )}
    </div>
  )
}
