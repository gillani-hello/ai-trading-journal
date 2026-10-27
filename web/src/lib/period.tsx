import { format, parseISO } from 'date-fns'
import { createContext, useContext, useMemo, useState, type ReactNode } from 'react'

export const PERIODS = [
  { value: 'week', label: '7D', long: 'Last 7 days' },
  { value: 'month', label: '30D', long: 'Last 30 days' },
  { value: 'quarter', label: '90D', long: 'Last 90 days' },
  { value: 'year', label: '1Y', long: 'Last 12 months' },
  { value: 'all', label: 'All', long: 'All time' },
] as const

export type Preset = (typeof PERIODS)[number]['value']

/** A rolling preset, or a custom inclusive date range (YYYY-MM-DD). */
export type Range = { kind: 'preset'; value: Preset } | { kind: 'custom'; from: string; to: string }

const KEY = 'tj.range'
const DEFAULT: Range = { kind: 'preset', value: 'month' }

function load(): Range {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return DEFAULT
    const r = JSON.parse(raw) as Range
    if (r.kind === 'preset' && PERIODS.some((p) => p.value === r.value)) return r
    if (r.kind === 'custom' && /^\d{4}-\d{2}-\d{2}$/.test(r.from) && /^\d{4}-\d{2}-\d{2}$/.test(r.to)) return r
  } catch {
    /* storage unavailable or malformed */
  }
  return DEFAULT
}

export function rangeLabel(r: Range): string {
  if (r.kind === 'preset') return PERIODS.find((p) => p.value === r.value)!.long
  const from = parseISO(r.from)
  const to = parseISO(r.to)
  if (r.from === r.to) return format(from, 'd MMM yyyy')
  const sameYear = from.getFullYear() === to.getFullYear()
  return `${format(from, sameYear ? 'd MMM' : 'd MMM yyyy')} – ${format(to, 'd MMM yyyy')}`
}

interface PeriodCtx {
  range: Range
  setRange: (r: Range) => void
  /** Query parameters for the API: `{period}` or `{from, to}`. */
  params: Record<string, string>
  label: string
}

const Ctx = createContext<PeriodCtx | null>(null)

export function PeriodProvider({ children }: { children: ReactNode }) {
  const [range, setState] = useState<Range>(load)
  const value = useMemo<PeriodCtx>(() => {
    const params: Record<string, string> = range.kind === 'preset' ? { period: range.value } : { from: range.from, to: range.to }
    return {
      range,
      params,
      label: rangeLabel(range),
      setRange: (r) => {
        setState(r)
        try {
          localStorage.setItem(KEY, JSON.stringify(r))
        } catch {
          /* storage unavailable */
        }
      },
    }
  }, [range])
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function usePeriod(): PeriodCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('usePeriod must be used inside PeriodProvider')
  return ctx
}
