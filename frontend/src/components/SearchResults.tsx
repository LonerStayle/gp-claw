import type { SearchResultItem } from "@/types"
import { Loader2 } from "lucide-react"

interface SearchResultsProps {
  query: string
  items: SearchResultItem[] | null
  total: number
  loading: boolean
  error: string | null
  canLoadMore: boolean
  onLoadMore: () => void
  onJump: (roomId: string, messageId: number, query: string) => void
}

const ROLE_BADGE: Record<string, string> = {
  user: "나",
  assistant: "AI",
  tool: "도구",
  system: "시스템",
}

function HighlightedSnippet({ snippet, query }: { snippet: string; query: string }) {
  if (!query) return <>{snippet}</>
  const lower = snippet.toLowerCase()
  const ql = query.toLowerCase()
  const idx = lower.indexOf(ql)
  if (idx < 0) return <>{snippet}</>
  return (
    <>
      {snippet.slice(0, idx)}
      <mark className="bg-yellow-200">{snippet.slice(idx, idx + query.length)}</mark>
      {snippet.slice(idx + query.length)}
    </>
  )
}

export function SearchResults({
  query, items, total, loading, error, canLoadMore, onLoadMore, onJump,
}: SearchResultsProps) {
  if (error) {
    return <div className="p-4 text-sm text-red-600">검색 중 오류: {error}</div>
  }
  if (items === null) {
    return null
  }
  if (items.length === 0) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-sm text-muted-foreground">
        결과 없음 — 다른 키워드 또는 필터를 시도해 보세요.
      </div>
    )
  }
  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-2">
      <p className="text-xs text-muted-foreground">총 {total}건</p>
      {items.map(it => (
        <button
          key={it.id}
          onClick={() => onJump(it.room_id, it.id, query)}
          className="block w-full rounded border p-2 text-left text-sm hover:bg-accent"
        >
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="truncate">{it.room_title}</span>
            <span>
              [{ROLE_BADGE[it.role] ?? it.role}] {new Date(it.created_at).toLocaleString()}
            </span>
          </div>
          <div className="mt-1 break-words">
            <HighlightedSnippet snippet={it.snippet} query={query} />
          </div>
        </button>
      ))}
      {canLoadMore && (
        <button
          onClick={onLoadMore}
          disabled={loading}
          className="w-full rounded border py-2 text-xs hover:bg-accent disabled:opacity-50"
        >
          {loading ? <Loader2 className="mx-auto h-4 w-4 animate-spin" /> : "더 보기"}
        </button>
      )}
    </div>
  )
}
