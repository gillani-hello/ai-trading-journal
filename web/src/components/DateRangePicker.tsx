import clsx from 'clsx'
import {
  endOfMonth,
  endOfWeek,
  format,
  startOfMonth,
  startOfWeek,
  startOfYear,
  subDays,
  subMonths,
  subWeeks,
} from 'date-fns'
import { CalendarRange, ChevronDown } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { PERIODS, rangeLabel, usePeriod } from '../lib/period'

const iso = (d: Date) => format(d, 'yyyy-MM-dd')

function quickRanges(today: Date): { label: string; from: Date; to: Date }[] {
  const week = { weekStartsOn: 1 as const }
  return [
    { label: 'Today', from: today, to: today },
    { label: 'Yesterday', from: subDays(today, 1), to: subDays(today, 1) },
    { label: 'This week', from: startOfWeek(today, week), to: today },
    { label: 'Last week', from: startOfWeek(subWeeks(today, 1), week), to: endOfWeek(subWeeks(today, 1), week) },
    { label: 'This month', from: startOfMonth(today), to: today },
    { label: 'Last month', from: startOfMonth(subMonths(today, 1)), to: endOfMonth(subMonths(today, 1)) },
    { label: 'Year to date', from: startOfYear(today), to: today },
  ]
}

/** Rolling presets plus a custom from/to range; the choice applies to every page. */
export function DateRangePicker() {
  const { range, setRange } = usePeriod()
  const [open, setOpen] = useState(false)
  const today = new Date()
  const [from, setFrom] = useState(range.kind === 'custom' ? range.from : iso(startOfMonth(today)))
  const [to, setTo] = useState(range.kind === 'custom' ? range.to : iso(today))
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const valid = from && to && from <= to
  const apply = (f: string, t: string) => {
    setRange({ kind: 'custom', from: f, to: t })
    setFrom(f)
    setTo(t)
    setOpen(false)
  }
  const custom = range.kind === 'custom'

  return (
    <div ref={ref} className="relative flex items-center gap-2">
      <div role="radiogroup" aria-label="Period" className="flex rounded-xl border border-border bg-surface/80 p-0.5 backdrop-blur">
        {PERIODS.map((p) => {
          const on = range.kind === 'preset' && range.value === p.value
          return (
            <button
              key={p.value}
              role="radio"
              aria-checked={on}
              title={p.long}
              onClick={() => setRange({ kind: 'preset', value: p.value })}
              className={clsx(
                'h-7 rounded-lg px-2.5 text-xs font-medium transition-colors',
                on ? 'bg-surface-3 text-ink shadow-sm' : 'text-muted hover:text-ink',
              )}
            >
              {p.label}
            </button>
          )
        })}
        <button
          role="radio"
          aria-checked={custom}
          aria-expanded={open}
          aria-haspopup="dialog"
          onClick={() => setOpen((o) => !o)}
          className={clsx(
            'inline-flex h-7 items-center gap-1.5 rounded-lg px-2.5 text-xs font-medium transition-colors',
            custom ? 'bg-accent/15 text-accent' : 'text-muted hover:text-ink',
          )}
        >
          <CalendarRange size={13} aria-hidden />
          {custom ? rangeLabel(range) : 'Custom'}
          <ChevronDown size={12} aria-hidden className={clsx('transition-transform', open && 'rotate-180')} />
        </button>
      </div>

      {open && (
        <div role="dialog" aria-label="Custom date range" className="absolute top-full right-0 z-30 mt-2 w-[min(92vw,420px)] rounded-2xl border border-border bg-surface-2 p-4 shadow-2xl shadow-black/50">
          <div className="grid grid-cols-[1fr_1.2fr] gap-4">
            <div className="space-y-0.5 border-r border-border pr-3">
              {quickRanges(today).map((q) => (
                <button
                  key={q.label}
                  onClick={() => apply(iso(q.from), iso(q.to))}
                  className="block w-full rounded-lg px-2.5 py-1.5 text-left text-sm text-ink-2 hover:bg-surface-3 hover:text-ink"
                >
                  {q.label}
                </button>
              ))}
            </div>
            <div className="space-y-3">
              <label className="block">
                <span className="mb-1 block text-xs text-muted">From</span>
                <input type="date" value={from} max={to || iso(today)} onChange={(e) => setFrom(e.target.value)} className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-ink [color-scheme:dark] focus:border-accent focus:outline-none" />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs text-muted">To</span>
                <input type="date" value={to} min={from} max={iso(today)} onChange={(e) => setTo(e.target.value)} className="w-full rounded-lg border border-border bg-surface px-2.5 py-1.5 text-sm text-ink [color-scheme:dark] focus:border-accent focus:outline-none" />
              </label>
              {!valid && from && to && <p className="text-xs text-neg">"From" must be on or before "To".</p>}
              <div className="flex justify-end gap-2 pt-1">
                <button onClick={() => setOpen(false)} className="h-8 rounded-lg px-3 text-sm text-ink-2 hover:bg-surface-3">
                  Cancel
                </button>
                <button
                  disabled={!valid}
                  onClick={() => apply(from, to)}
                  className="h-8 rounded-lg bg-accent-strong px-3 text-sm font-medium text-white hover:bg-accent disabled:opacity-50"
                >
                  Apply
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
