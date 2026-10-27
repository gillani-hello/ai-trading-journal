import type {
  CalendarMonth,
  Dashboard,
  DayDetail,
  DayNote,
  Flag,
  Insight,
  InstrumentCard,
  InstrumentDetail,
  Journal,
  McpConfig,
  Report,
  ReportListItem,
  Settings,
  Status,
  SyncResult,
  Tags,
  Trade,
  TradeDetail,
} from './types'

export type Params = Record<string, string | number | boolean | null | undefined>

function qs(params?: Params): string {
  if (!params) return ''
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

async function request<T>(method: string, path: string, body?: unknown, params?: Params): Promise<T> {
  const init: RequestInit = { method, headers: {} }
  if (body instanceof FormData) {
    init.body = body
  } else if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers = { 'Content-Type': 'application/json' }
  }
  const res = await fetch(`/api${path}${qs(params)}`, init)
  if (!res.ok) {
    let detail = res.statusText
    try {
      const data = await res.json()
      detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch {
      /* keep statusText */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const get = <T,>(path: string, params?: Params) => request<T>('GET', path, undefined, params)

export const api = {
  status: () => get<Status>('/status'),
  sync: (force = false) => request<SyncResult>('POST', '/sync', undefined, { force }),
  dashboard: (p: Params) => get<Dashboard>('/dashboard', p),
  trades: (p: Params) => get<{ total: number; items: Trade[] }>('/trades', p),
  trade: (id: number) => get<TradeDetail>(`/trades/${id}`),
  patchJournal: (id: number, body: Partial<Journal>) => request<TradeDetail>('PATCH', `/trades/${id}/journal`, body),
  createTrade: (body: Record<string, unknown>) =>
    request<{ trade: Trade; warnings: string[] }>('POST', '/trades', body),
  deleteTrade: (id: number) => request<{ deleted: number }>('DELETE', `/trades/${id}`),
  uploadScreenshot: (id: number, file: File, caption?: string) => {
    const fd = new FormData()
    fd.append('file', file)
    if (caption) fd.append('caption', caption)
    return request<{ id: number; url: string }>('POST', `/trades/${id}/screenshots`, fd)
  },
  deleteScreenshot: (id: number) => request<{ deleted: number }>('DELETE', `/screenshots/${id}`),
  calendar: (month: string) => get<CalendarMonth>('/calendar', { month }),
  day: (date: string) => get<DayDetail>(`/day/${date}`),
  putDayNote: (date: string, body: Partial<DayNote>) => request<DayNote>('PUT', `/day-notes/${date}`, body),
  instruments: (p: Params) => get<InstrumentCard[]>('/instruments', p),
  instrument: (symbol: string, p: Params) => get<InstrumentDetail>(`/instruments/${encodeURIComponent(symbol)}`, p),
  insights: (p: Params) => get<Insight[]>('/insights', p),
  behavior: (p: Params) => get<Flag[]>('/behavior', p),
  reports: (symbol?: string) => get<ReportListItem[]>('/ai-reports', { symbol }),
  report: (id: number) => get<Report>(`/ai-reports/${id}`),
  deleteReport: (id: number) => request<{ deleted: number }>('DELETE', `/ai-reports/${id}`),
  settings: () => get<Settings>('/settings'),
  patchSettings: (body: Partial<Settings>) => request<Settings>('PATCH', '/settings', body),
  timezones: () => get<string[]>('/timezones'),
  tags: () => get<Tags>('/tags'),
  putTags: (category: string, names: string[]) => request<string[]>('PUT', `/tags/${category}`, names),
  mcpConfig: () => get<McpConfig>('/mcp-config'),
}
