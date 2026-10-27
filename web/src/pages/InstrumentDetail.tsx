import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowLeft, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { BreakdownBars, EquityChart } from '../components/charts'
import { TradeTable } from '../components/TradeTable'
import { Card, Empty, ErrorBox, InsightRow, PageHeader, PeriodPicker, Pnl, SeverityBadge, Spinner, Stat, VerdictBadge } from '../components/ui'
import { api } from '../lib/api'
import { dt, minutes, money, pct, pnlClass, ratio, rMult } from '../lib/format'
import { usePeriod } from '../lib/period'

const TABS = [
  ['session', 'Session'],
  ['weekday', 'Weekday'],
  ['direction', 'Direction'],
  ['setup', 'Setup'],
  ['close_reason', 'Exit'],
  ['hold', 'Hold time'],
  ['emotion', 'Emotion'],
  ['mistake', 'Mistake'],
] as const

function AiList({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  if (!items.length) return null
  return (
    <div>
      <div className={clsx('text-xs font-medium tracking-wide uppercase', tone)}>{title}</div>
      <ul className="mt-1.5 list-disc space-y-1 pl-5 text-sm text-ink-2">
        {items.map((x, n) => (
          <li key={n}>{x}</li>
        ))}
      </ul>
    </div>
  )
}

export function InstrumentDetailPage() {
  const symbol = useParams().symbol!
  const { params, label } = usePeriod()
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('session')
  const { data, isLoading, error } = useQuery({ queryKey: ['instrument', symbol, params], queryFn: () => api.instrument(symbol, params) })
  const { data: trades } = useQuery({
    queryKey: ['trades', { instrument: symbol, ...params, limit: 25 }],
    queryFn: () => api.trades({ instrument: symbol, ...params, limit: 25, status: 'all' }),
  })

  return (
    <>
      <Link to="/instruments" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft size={14} /> Instruments
      </Link>
      <PageHeader title={<span className="flex items-center gap-2.5">{symbol.toUpperCase()} {data && <VerdictBadge verdict={data.verdict} />}</span>} sub={label}>
        <PeriodPicker />
      </PageHeader>
      {isLoading && <Spinner />}
      {error && <ErrorBox error={error} />}
      {data && data.stats.trades === 0 && <Empty title={`No closed ${symbol} trades in this period`} />}
      {data && data.stats.trades > 0 && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <Stat label="Net P&L" value={<Pnl value={data.stats.net_pnl} />} sub={`${data.stats.trades} trades`} />
            <Stat label="Win rate" value={pct(data.stats.win_rate)} sub={`${data.stats.long_trades} long · ${data.stats.short_trades} short`} />
            <Stat label="Profit factor" value={ratio(data.stats.profit_factor)} sub={`Payoff ${ratio(data.stats.payoff_ratio)}`} />
            <Stat label="Expectancy" value={<span className={pnlClass(data.stats.expectancy)}>{money(data.stats.expectancy)}</span>} sub="per trade" />
            <Stat label="Avg R" value={<span className={pnlClass(data.stats.avg_r)}>{rMult(data.stats.avg_r)}</span>} sub={`Total ${rMult(data.stats.total_r)}`} />
            <Stat label="Hold" value={minutes(data.stats.avg_hold_win_min)} sub={`winners · losers ${minutes(data.stats.avg_hold_loss_min)}`} />
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Equity curve" className="lg:col-span-2">
              <EquityChart data={data.equity} height={220} />
            </Card>
            <Card title={<span className="inline-flex items-center gap-1.5"><Sparkles size={14} className="text-accent" /> AI coach on {data.instrument}</span>}>
              {data.ai ? (
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-sm font-medium">{data.ai.headline}</p>
                    <VerdictBadge verdict={data.ai.verdict} />
                  </div>
                  <AiList title="Doing well" items={data.ai.doing_well} tone="text-pos" />
                  <AiList title="Going wrong" items={data.ai.going_wrong} tone="text-neg" />
                  <AiList title="Improve" items={data.ai.improvements} tone="text-accent" />
                  <AiList title="Rules" items={data.ai.rules} tone="text-warn" />
                  <Link to={`/coach/${data.ai.report_id}`} className="block text-xs text-muted hover:text-ink">
                    From “{data.ai.report_title}” · {dt(data.ai.created_at, 'd MMM yyyy')}
                  </Link>
                </div>
              ) : (
                <p className="text-sm text-muted">
                  No AI review of {data.instrument} yet. In Claude, run the <code className="text-ink-2">instrument_review</code> prompt with symbol <b className="text-ink">{data.instrument}</b>.
                </p>
              )}
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-3">
            <Card title="Breakdown" className="lg:col-span-2">
              <div className="mb-3 flex flex-wrap gap-1">
                {TABS.map(([k, label]) => (
                  <button
                    key={k}
                    onClick={() => setTab(k)}
                    className={clsx('rounded-md px-2.5 py-1 text-xs', tab === k ? 'bg-surface-3 text-ink' : 'text-muted hover:text-ink')}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {data.breakdowns[tab]?.length ? <BreakdownBars data={data.breakdowns[tab]} /> : <div className="py-6 text-sm text-muted">No data for this breakdown.</div>}
            </Card>
            <Card title="What the numbers say">
              <ul className="divide-y divide-border">
                {data.insights.map((i, n) => (
                  <InsightRow key={n} insight={i} />
                ))}
              </ul>
            </Card>
          </div>

          {data.flags.length > 0 && (
            <Card title="Red flags">
              <ul className="grid gap-3 md:grid-cols-2">
                {data.flags.map((f) => (
                  <li key={f.code + f.title} className="rounded-lg border border-border p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-sm font-medium">{f.title}</span>
                      <SeverityBadge severity={f.severity} />
                    </div>
                    <p className="mt-1 text-xs leading-relaxed text-muted">{f.description}</p>
                  </li>
                ))}
              </ul>
            </Card>
          )}

          {trades && trades.items.length > 0 && (
            <div>
              <div className="mb-2 flex items-center justify-between">
                <h2 className="text-sm font-medium text-ink-2">Recent trades</h2>
                <Link to={`/trades?instrument=${data.instrument}`} className="text-xs text-accent hover:underline">
                  All {trades.total}
                </Link>
              </div>
              <TradeTable trades={trades.items} showInstrument={false} />
            </div>
          )}
        </div>
      )}
    </>
  )
}
