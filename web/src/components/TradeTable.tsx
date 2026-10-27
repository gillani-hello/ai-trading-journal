import clsx from 'clsx'
import { ArrowDown, ArrowUp, Image, PenLine } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { dt, duration, price, rMult } from '../lib/format'
import type { Trade } from '../lib/types'
import { Badge, Pnl, SideBadge } from './ui'

const SORTABLE: Record<string, string> = {
  Closed: 'time',
  Instrument: 'instrument',
  Size: 'volume',
  R: 'r_multiple',
  Net: 'net_pnl',
  Held: 'holding',
}

export function TradeTable({ trades, sort, onSort, showInstrument = true }: { trades: Trade[]; sort?: string; onSort?: (s: string) => void; showInstrument?: boolean }) {
  const navigate = useNavigate()
  const cols = ['Closed', ...(showInstrument ? ['Instrument'] : []), 'Side', 'Size', 'Entry → Exit', 'SL', 'R', 'Net', 'Held', 'Setup', 'Tags']
  const active = sort?.replace('-', '')
  return (
    <div className="overflow-x-auto rounded-2xl border border-border bg-gradient-to-b from-surface-2/60 to-surface shadow-[inset_0_1px_0_0_rgb(255_255_255/0.04)]">
      <table className="w-full min-w-[960px] text-sm">
        <thead className="sticky top-0 z-10 bg-surface-2/95 backdrop-blur">
          <tr className="border-b border-border text-left text-[11px] tracking-wide text-muted uppercase">
            {cols.map((c) => {
              const key = SORTABLE[c]
              const isActive = key && key === active
              return (
                <th key={c} className={clsx('px-3 py-3 font-semibold', ['Size', 'R', 'Net', 'Held'].includes(c) && 'text-right')}>
                  {key && onSort ? (
                    <button
                      className={clsx('inline-flex items-center gap-1 uppercase hover:text-ink', isActive && 'text-ink')}
                      onClick={() => onSort(isActive && sort?.startsWith('-') ? key : `-${key}`)}
                    >
                      {c}
                      {isActive && (sort?.startsWith('-') ? <ArrowDown size={12} /> : <ArrowUp size={12} />)}
                    </button>
                  ) : (
                    c
                  )}
                </th>
              )
            })}
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => {
            const net = t.status === 'open' ? t.floating_pnl : t.net_pnl
            const tags = [...t.journal.emotions, ...t.journal.mistakes]
            return (
              <tr
                key={t.id}
                onClick={() => navigate(`/trades/${t.id}`)}
                className="cursor-pointer border-b border-border/50 transition-colors last:border-0 hover:bg-white/[0.03]"
              >
                <td className="px-3 py-2.5 whitespace-nowrap text-ink-2">
                  {t.status === 'open' ? <Badge tone="warn">Open</Badge> : dt(t.close_time, 'd MMM HH:mm')}
                </td>
                {showInstrument && (
                  <td className="px-3 py-2 font-medium whitespace-nowrap">
                    <span className="mr-2 inline-grid size-6 place-items-center rounded-lg bg-surface-3 align-middle text-[10px] font-bold text-ink-2 ring-1 ring-white/5">
                      {t.instrument.slice(0, 2)}
                    </span>
                    {t.instrument}
                    {t.source === 'manual' && (
                      <PenLine size={12} className="ml-1.5 inline text-muted" aria-label="Logged manually" />
                    )}
                  </td>
                )}
                <td className="px-3 py-2">
                  <SideBadge direction={t.direction} />
                </td>
                <td className="num px-3 py-2 text-right">{t.volume || '—'}</td>
                <td className="num px-3 py-2 whitespace-nowrap text-ink-2">
                  {price(t.entry_price)} → {price(t.exit_price)}
                </td>
                <td className="num px-3 py-2 text-ink-2" title={t.sl_source === 'entry' ? 'Stop on the order' : t.sl_source ? 'Stop added after entry' : 'No protective stop'}>
                  {price(t.risk_sl)}
                  {t.sl_source && t.sl_source !== 'entry' && <span className="ml-0.5 text-warn">*</span>}
                </td>
                <td className={clsx('num px-3 py-2 text-right', (t.r_multiple ?? 0) < 0 ? 'text-neg' : 'text-ink-2')}>{rMult(t.r_multiple)}</td>
                <td className="px-3 py-2 text-right">
                  <span
                    className={clsx(
                      'inline-block min-w-20 rounded-lg px-2 py-0.5 font-semibold',
                      (net ?? 0) > 0 ? 'bg-pos/10' : (net ?? 0) < 0 ? 'bg-neg/10' : 'bg-surface-3/60',
                    )}
                  >
                    <Pnl value={net} />
                  </span>
                </td>
                <td className="num px-3 py-2 text-right whitespace-nowrap text-ink-2">{duration(t.holding_seconds)}</td>
                <td className="max-w-36 truncate px-3 py-2 text-ink-2">{t.journal.setup ?? <span className="text-muted">—</span>}</td>
                <td className="px-3 py-2">
                  <div className="flex max-w-56 items-center gap-1 overflow-hidden">
                    {tags.slice(0, 3).map((tag) => (
                      <Badge key={tag} tone={t.journal.mistakes.includes(tag) ? 'neg' : 'neutral'}>
                        {tag}
                      </Badge>
                    ))}
                    {tags.length > 3 && <span className="text-xs text-muted">+{tags.length - 3}</span>}
                    {t.screenshot_count > 0 && <Image size={13} className="shrink-0 text-muted" aria-label="Has screenshots" />}
                  </div>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
