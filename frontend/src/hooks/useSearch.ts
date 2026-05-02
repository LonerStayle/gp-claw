import { useEffect, useState } from "react"
import type { SearchFilter, SearchResponse } from "@/types"

const PAGE_SIZE = 50

export function useSearch(filter: SearchFilter) {
  const [data, setData] = useState<SearchResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [offset, setOffset] = useState(0)

  useEffect(() => { setOffset(0) }, [filter.q, filter.roomIds, filter.roles, filter.dateFrom, filter.dateTo])

  useEffect(() => {
    if (!filter.q || filter.q.length === 0) {
      setData(null)
      return
    }
    const handle = setTimeout(async () => {
      setLoading(true); setError(null)
      try {
        const params = new URLSearchParams()
        params.set("q", filter.q)
        filter.roomIds.forEach(r => params.append("room_id", r))
        filter.roles.forEach(r => params.append("role", r))
        if (filter.dateFrom) params.set("from", filter.dateFrom)
        if (filter.dateTo) params.set("to", filter.dateTo)
        params.set("limit", String(PAGE_SIZE))
        params.set("offset", String(offset))
        const res = await fetch(`/search/messages?${params}`)
        if (!res.ok) throw new Error(`${res.status}`)
        const body: SearchResponse = await res.json()
        // append-mode for offset>0, replace for offset=0
        setData(prev => offset === 0 || !prev
          ? body
          : { total: body.total, items: [...prev.items, ...body.items] })
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e))
      } finally {
        setLoading(false)
      }
    }, 250)
    return () => clearTimeout(handle)
  }, [filter.q, filter.roomIds, filter.roles, filter.dateFrom, filter.dateTo, offset])

  return {
    data,
    loading,
    error,
    canLoadMore: data ? data.items.length < data.total : false,
    loadMore: () => setOffset(o => o + PAGE_SIZE),
  }
}
