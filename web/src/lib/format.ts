import { format, formatDistanceToNowStrict, parseISO } from 'date-fns'

const MINUS = '−'

export function money(v: number | null | undefined, opts: { sign?: boolean; decimals?: number } = {}): string {
  if (v === null || v === undefined) return '—'
  const { sign = true, decimals = Math.abs(v) >= 1000 ? 0 : 2 } = opts
  const body = Math.abs(v).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
  if (v < 0) return `${MINUS}${body}`
  return sign && v > 0 ? `+${body}` : body
}

export function compactMoney(v: number): string {
  const a = Math.abs(v)
  const body = a >= 1000 ? `${(a / 1000).toFixed(a >= 10000 ? 0 : 1)}k` : a.toFixed(0)
  return v < 0 ? `${MINUS}${body}` : v > 0 ? `+${body}` : body
}

/** Account amounts: currency symbol, always 2 decimals, minus sign only. */
export function currency(v: number | null | undefined, ccy = 'USD'): string {
  if (v === null || v === undefined) return '—'
  try {
    return new Intl.NumberFormat(undefined, { style: 'currency', currency: ccy, currencyDisplay: 'narrowSymbol', minimumFractionDigits: 2 }).format(v).replace('-', MINUS)
  } catch {
    return `${money(v, { sign: false, decimals: 2 })} ${ccy}`
  }
}

/** Axis ticks for absolute values (balances): 23.8k. */
export const abbr = (v: number) => (Math.abs(v) >= 1000 ? `${(v / 1000).toFixed(Math.abs(v) >= 100000 ? 0 : 1)}k` : v.toFixed(0))

export const pct = (v: number | null | undefined, decimals = 0) =>
  v === null || v === undefined ? '—' : `${(v * 100).toFixed(decimals)}%`

export const ratio = (v: number | null | undefined, decimals = 2) =>
  v === null || v === undefined ? '—' : v.toFixed(decimals)

export function rMult(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${v < 0 ? MINUS : v > 0 ? '+' : ''}${Math.abs(v).toFixed(2)}R`
}

export function price(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  const abs = Math.abs(v)
  const decimals = abs >= 1000 ? 2 : abs >= 10 ? 3 : 5
  return v.toFixed(decimals).replace(/0+$/, '').replace(/\.$/, '')
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  const m = Math.round(seconds / 60)
  if (m < 60) return `${m}m`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ${m % 60}m`
  return `${Math.floor(h / 24)}d ${h % 24}h`
}

export const minutes = (v: number | null | undefined) => (v === null || v === undefined ? '—' : duration(v * 60))

export const dt = (iso: string | null | undefined, f = 'd MMM yyyy HH:mm') => (iso ? format(parseISO(iso), f) : '—')

export const ago = (iso: string | null | undefined) => (iso ? `${formatDistanceToNowStrict(parseISO(iso))} ago` : 'never')

export const pnlClass = (v: number | null | undefined) =>
  v === null || v === undefined || v === 0 ? 'text-ink-2' : v > 0 ? 'text-pos' : 'text-neg'

export const titleCase = (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

const CLOSE_REASONS: Record<string, string> = {
  sl: 'Stop-loss',
  tp: 'Take-profit',
  manual: 'Manual',
  expert: 'EA',
  stop_out: 'Stop-out',
  reversal: 'Reversal',
}

export const closeReason = (r: string | null | undefined) => (r ? (CLOSE_REASONS[r] ?? titleCase(r)) : '—')
