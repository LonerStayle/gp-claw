import { Search } from "lucide-react"
import type { MessageRole, SearchFilter } from "@/types"
import type { Room } from "@/types"

interface SearchBarProps {
  rooms: Room[]
  filter: SearchFilter
  onChange: (next: SearchFilter) => void
  onClear: () => void
}

const ROLES: MessageRole[] = ["user", "assistant", "tool", "system"]
const ROLE_LABELS: Record<MessageRole, string> = {
  user: "내가 보낸",
  assistant: "AI 응답",
  tool: "도구",
  system: "시스템",
}

const QUICK_RANGES: { label: string; days: number | null }[] = [
  { label: "전체", days: null },
  { label: "오늘", days: 0 },
  { label: "최근 7일", days: 7 },
  { label: "최근 30일", days: 30 },
]

function isoDaysAgo(days: number): string {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  d.setDate(d.getDate() - days)
  return d.toISOString()
}

export function SearchBar({ rooms, filter, onChange, onClear }: SearchBarProps) {
  const toggleRole = (role: MessageRole) => {
    const next = filter.roles.includes(role)
      ? filter.roles.filter(r => r !== role)
      : [...filter.roles, role]
    onChange({ ...filter, roles: next })
  }
  const toggleRoom = (id: string) => {
    const next = filter.roomIds.includes(id)
      ? filter.roomIds.filter(r => r !== id)
      : [...filter.roomIds, id]
    onChange({ ...filter, roomIds: next })
  }
  const setRange = (days: number | null) => {
    if (days === null) {
      onChange({ ...filter, dateFrom: undefined, dateTo: undefined })
    } else {
      onChange({ ...filter, dateFrom: isoDaysAgo(days), dateTo: undefined })
    }
  }

  return (
    <div className="border-b bg-background p-3 space-y-2">
      <div className="flex items-center gap-2">
        <Search className="h-4 w-4 text-muted-foreground" />
        <input
          type="text"
          value={filter.q}
          onChange={e => onChange({ ...filter, q: e.target.value })}
          placeholder="대화 전체에서 검색…"
          className="flex-1 rounded border px-2 py-1 text-sm outline-none focus:ring"
          aria-label="검색어"
        />
        {filter.q && (
          <button onClick={onClear} className="text-xs text-muted-foreground underline">
            지우기
          </button>
        )}
      </div>

      {filter.q && (
        <div className="flex flex-wrap gap-2 text-xs">
          {ROLES.map(r => (
            <label key={r} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={filter.roles.includes(r)}
                onChange={() => toggleRole(r)}
              />
              {ROLE_LABELS[r]}
            </label>
          ))}
          <span className="mx-2 text-muted-foreground">|</span>
          {QUICK_RANGES.map(qr => (
            <button
              key={qr.label}
              onClick={() => setRange(qr.days)}
              className="rounded border px-2 py-0.5 hover:bg-accent"
            >
              {qr.label}
            </button>
          ))}
          <span className="mx-2 text-muted-foreground">|</span>
          <details className="relative">
            <summary className="cursor-pointer">방 필터({filter.roomIds.length || "전체"})</summary>
            <div className="absolute z-10 mt-1 max-h-48 w-56 overflow-y-auto rounded border bg-background p-2 shadow">
              {rooms.map(r => (
                <label key={r.id} className="flex items-center gap-1 py-0.5">
                  <input
                    type="checkbox"
                    checked={filter.roomIds.includes(r.id)}
                    onChange={() => toggleRoom(r.id)}
                  />
                  <span className="truncate">{r.title}</span>
                </label>
              ))}
            </div>
          </details>
        </div>
      )}
    </div>
  )
}
