import { format, parseISO } from 'date-fns'
import type { ReactNode } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { abbr, compactMoney, currency, money, pct, rMult } from '../lib/format'
import type { BalancePoint, DailyPoint, EquityPoint, Group, Summary } from '../lib/types'

const C = {
  accent: '#3987e5',
  pos: '#0ca30c',
  neg: '#e66767',
  grid: '#2c2c2a',
  baseline: '#383835',
  muted: '#898781',
  ink2: '#c3c2b7',
}

const axis = { stroke: C.baseline, tick: { fill: C.muted, fontSize: 11 }, tickLine: false }

const DAY = 86_400_000

/** A real time axis: ticks at local midnights (or every few hours for short ranges). */
function timeAxis(times: number[]) {
  const lo = Math.min(...times)
  const hi = Math.max(...times)
  const span = hi - lo
  if (span <= 2 * DAY) {
    const step = span <= DAY / 2 ? 3_600_000 * 2 : 3_600_000 * 6
    const ticks = []
    for (let t = Math.ceil(lo / step) * step; t <= hi; t += step) ticks.push(t)
    return { ticks, fmt: (v: number) => format(v, 'HH:mm') }
  }
  const stepDays = Math.max(1, Math.ceil(span / DAY / 8))
  const first = new Date(lo)
  first.setHours(0, 0, 0, 0)
  const ticks = []
  for (let d = new Date(first); d.getTime() <= hi; d.setDate(d.getDate() + stepDays)) {
    if (d.getTime() >= lo) ticks.push(d.getTime())
  }
  return { ticks, fmt: (v: number) => format(v, span > 300 * DAY ? 'MMM yy' : 'd MMM') }
}

function TipBox({ title, children }: { title: ReactNode; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface-2 px-3 py-2 text-xs shadow-xl">
      <div className="mb-1 font-medium text-ink">{title}</div>
      <div className="space-y-0.5 text-ink-2">{children}</div>
    </div>
  )
}

function Row({ label, value, tone }: { label: string; value: ReactNode; tone?: number }) {
  const cls = tone === undefined || tone === 0 ? 'text-ink' : tone > 0 ? 'text-pos' : 'text-neg'
  return (
    <div className="flex justify-between gap-4">
      <span className="text-muted">{label}</span>
      <span className={`num ${cls}`}>{value}</span>
    </div>
  )
}

export function EquityChart({ data, height = 240 }: { data: EquityPoint[]; height?: number }) {
  const points = (data.length ? [{ time: data[0].time, equity: 0, pnl: 0, trade_id: 0 }, ...data] : []).map((p) => ({ ...p, t: Date.parse(p.time) }))
  const { ticks, fmt } = timeAxis(points.length ? points.map((p) => p.t) : [Date.now()])
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="eq" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.accent} stopOpacity={0.25} />
            <stop offset="100%" stopColor={C.accent} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} ticks={ticks} tickFormatter={fmt} {...axis} />
        <YAxis {...axis} axisLine={false} width={52} tickFormatter={(v: number) => compactMoney(v)} />
        <ReferenceLine y={0} stroke={C.baseline} />
        <Tooltip
          cursor={{ stroke: C.muted, strokeDasharray: '3 3' }}
          content={({ active, payload }) => {
            const p = active && payload?.[0]?.payload
            if (!p || !p.trade_id) return null
            return (
              <TipBox title={format(parseISO(p.time), 'd MMM yyyy HH:mm')}>
                <Row label="Equity" value={money(p.equity)} tone={p.equity} />
                <Row label="Trade" value={money(p.pnl)} tone={p.pnl} />
              </TipBox>
            )
          }}
        />
        <Area type="stepAfter" dataKey="equity" baseValue={0} stroke={C.accent} strokeWidth={2} fill="url(#eq)" activeDot={{ r: 4, stroke: '#1a1a19', strokeWidth: 2 }} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

export function DailyBars({ data, height = 200 }: { data: DailyPoint[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="date" {...axis} tickFormatter={(v: string) => format(parseISO(v), 'd MMM')} minTickGap={32} />
        <YAxis {...axis} axisLine={false} width={52} tickFormatter={(v: number) => compactMoney(v)} />
        <ReferenceLine y={0} stroke={C.baseline} />
        <Tooltip
          cursor={{ fill: 'rgba(255,255,255,0.04)' }}
          content={({ active, payload }) => {
            const p = active && (payload?.[0]?.payload as DailyPoint | undefined)
            if (!p) return null
            return (
              <TipBox title={format(parseISO(p.date), 'EEE d MMM yyyy')}>
                <Row label="Net" value={money(p.net_pnl)} tone={p.net_pnl} />
                <Row label="Trades" value={`${p.trades} (${p.wins}W / ${p.losses}L)`} />
              </TipBox>
            )
          }}
        />
        <Bar dataKey="net_pnl" radius={[4, 4, 0, 0]} maxBarSize={18} isAnimationActive={false}>
          {data.map((d) => (
            <Cell key={d.date} fill={d.net_pnl >= 0 ? C.pos : C.neg} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}

/** Diverging net P&L bars per group (instrument, session, weekday…); every row is labelled, so no hover is needed. */
export function BreakdownBars({ data, sortByValue = false }: { data: Group[]; sortByValue?: boolean }) {
  const rows = sortByValue ? [...data].sort((a, b) => b.net_pnl - a.net_pnl) : data
  const max = Math.max(...rows.map((g) => Math.abs(g.net_pnl)), 1)
  return (
    <ul className="space-y-2.5" aria-label="Net P&L by group">
      {rows.map((g) => {
        const w = (Math.abs(g.net_pnl) / max) * 50
        return (
          <li key={g.key} className="grid grid-cols-[minmax(0,9.5rem)_minmax(0,1fr)_4.5rem] items-center gap-3">
            <div className="min-w-0">
              <div className="truncate text-sm text-ink">{g.key}</div>
              <div className="num truncate text-[11px] text-muted">
                {g.trades} trades · {pct(g.win_rate)} · {rMult(g.avg_r)}
              </div>
            </div>
            <div className="relative h-2.5" aria-hidden>
              <div className="absolute inset-y-[-4px] left-1/2 w-px bg-baseline" />
              <div
                className="absolute inset-y-0"
                style={{
                  ...(g.net_pnl >= 0 ? { left: '50%', borderRadius: '0 4px 4px 0' } : { right: '50%', borderRadius: '4px 0 0 4px' }),
                  width: `${w}%`,
                  background: g.net_pnl >= 0 ? C.pos : C.neg,
                }}
              />
            </div>
            <div className="num text-right text-sm text-ink-2">{compactMoney(g.net_pnl)}</div>
          </li>
        )
      })}
    </ul>
  )
}

/** MFE/MAE strip for one trade: worst point, best point and where it closed, in points. */
export function ExcursionBar({ mae, mfe, result }: { mae: number; mfe: number; result: number }) {
  const span = Math.max(mae + mfe, 1)
  const zero = (mae / span) * 100
  const at = ((mae + result) / span) * 100
  const kept = mfe > 0 && result > 0 ? result / mfe : null
  return (
    <div>
      <div className="relative h-3 rounded-full bg-surface-3" role="img" aria-label={`Max adverse ${mae.toFixed(0)} points, max favourable ${mfe.toFixed(0)} points, closed at ${result.toFixed(0)} points`}>
        <div className="absolute inset-y-0 left-0 rounded-l-full bg-neg/50" style={{ width: `${zero}%` }} />
        <div className="absolute inset-y-0 rounded-r-full bg-pos/50" style={{ left: `${zero}%`, right: 0 }} />
        <div className="absolute -inset-y-1 w-0.5 bg-ink-2" style={{ left: `${zero}%` }} />
        <div className="absolute -top-1.5 h-6 w-1.5 -translate-x-1/2 rounded-full border-2 border-surface bg-ink" style={{ left: `${Math.min(Math.max(at, 0), 100)}%` }} />
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted">
        <span className="num">MAE −{mae.toFixed(0)} pts</span>
        <span className="num text-ink-2">
          Closed {result >= 0 ? '+' : '−'}
          {Math.abs(result).toFixed(0)} pts{kept !== null && ` · kept ${(kept * 100).toFixed(0)}% of the best`}
        </span>
        <span className="num">MFE +{mfe.toFixed(0)} pts</span>
      </div>
    </div>
  )
}

function balanceDomain(data: BalancePoint[]): [number, number] {
  const values = data.map((d) => d.balance)
  const lo = Math.min(...values)
  const hi = Math.max(...values)
  const pad = Math.max((hi - lo) * 0.12, Math.abs(hi) * 0.002, 1)
  return [lo - pad, hi + pad]
}

/** Account balance over time. Drawn as steps: the balance only changes when a deal books. */
export function BalanceChart({ data, ccy, height = 260 }: { data: BalancePoint[]; ccy: string; height?: number }) {
  if (data.length === 0) return <div className="grid h-40 place-items-center text-sm text-muted">No balance changes in this range.</div>
  const opening = data[0].balance
  const points = data.map((p) => ({ ...p, t: Date.parse(p.time) }))
  const { ticks, fmt } = timeAxis(points.map((p) => p.t))
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="bal" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.accent} stopOpacity={0.28} />
            <stop offset="100%" stopColor={C.accent} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="t" type="number" scale="time" domain={['dataMin', 'dataMax']} ticks={ticks} tickFormatter={fmt} {...axis} />
        <YAxis {...axis} axisLine={false} width={52} domain={balanceDomain(data)} tickFormatter={abbr} />
        <ReferenceLine y={opening} stroke={C.muted} strokeDasharray="4 4" />
        <Tooltip
          cursor={{ stroke: C.muted, strokeDasharray: '3 3' }}
          content={({ active, payload }) => {
            const p = active && (payload?.[0]?.payload as BalancePoint | undefined)
            if (!p) return null
            return (
              <TipBox title={format(parseISO(p.time), 'd MMM yyyy HH:mm')}>
                <Row label="Balance" value={currency(p.balance, ccy)} />
                {p.kind !== 'open' && <Row label={p.kind === 'cash' ? 'Deposit / withdrawal' : 'Deal'} value={money(p.change)} tone={p.change} />}
                <Row label="Since start" value={money(p.balance - opening)} tone={p.balance - opening} />
              </TipBox>
            )
          }}
        />
        <Area type="stepAfter" dataKey="balance" baseValue="dataMin" stroke={C.accent} strokeWidth={2} fill="url(#bal)" activeDot={{ r: 4, stroke: '#1a1a19', strokeWidth: 2 }} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/** Tiny balance line for the account card; no axes, the card states the numbers. */
export function Sparkline({ data, height = 56 }: { data: BalancePoint[]; height?: number }) {
  if (data.length < 2) return null
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="spark" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={C.accent} stopOpacity={0.35} />
            <stop offset="100%" stopColor={C.accent} stopOpacity={0} />
          </linearGradient>
        </defs>
        <YAxis hide domain={balanceDomain(data)} />
        <Area type="stepAfter" dataKey="balance" baseValue="dataMin" stroke={C.accent} strokeWidth={2} fill="url(#spark)" dot={false} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  )
}

/** Wins / losses / breakeven as a ring with the win rate in the middle; counts are labelled beside it. */
export function WinRing({ summary, size = 132 }: { summary: Summary; size?: number }) {
  const parts = [
    { n: summary.wins, color: C.pos },
    { n: summary.losses, color: C.neg },
    { n: summary.breakeven, color: C.muted },
  ].filter((p) => p.n > 0)
  const total = parts.reduce((s, p) => s + p.n, 0)
  const stroke = 12
  const r = (size - stroke) / 2
  const circ = 2 * Math.PI * r
  const gap = parts.length > 1 ? 3 : 0
  let offset = 0
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label={`Win rate ${pct(summary.win_rate)}: ${summary.wins} wins, ${summary.losses} losses, ${summary.breakeven} breakeven`}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={C.grid} strokeWidth={stroke} />
      {total > 0 &&
        parts.map((p, i) => {
          const len = (p.n / total) * circ
          const el = (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={p.color}
              strokeWidth={stroke}
              strokeLinecap="butt"
              strokeDasharray={`${Math.max(len - gap, 0)} ${circ}`}
              strokeDashoffset={-offset}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
            />
          )
          offset += len
          return el
        })}
      <text x="50%" y="47%" textAnchor="middle" fill="#f0efec" fontSize={24} fontWeight={600}>
        {pct(summary.win_rate)}
      </text>
      <text x="50%" y="62%" textAnchor="middle" fill={C.muted} fontSize={11}>
        win rate
      </text>
    </svg>
  )
}
