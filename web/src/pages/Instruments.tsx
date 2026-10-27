import { useQuery } from '@tanstack/react-query'
import { AlertTriangle } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Empty, ErrorBox, InsightRow, PageHeader, PeriodPicker, Pnl, Spinner, VerdictBadge } from '../components/ui'
import { api } from '../lib/api'
import { compactMoney, pct, ratio, rMult } from '../lib/format'
import { usePeriod } from '../lib/period'
import type { Group } from '../lib/types'

function SessionStrip({ sessions }: { sessions: Group[] }) {
  const max = Math.max(...sessions.map((s) => Math.abs(s.net_pnl)), 1)
  return (
    <div className="space-y-1">
      {sessions.map((s) => (
        <div key={s.key} className="flex items-center gap-2 text-xs">
          <span className="w-16 shrink-0 text-muted">{s.key}</span>
          <div className="relative h-1.5 flex-1 rounded-full bg-surface-3" aria-hidden>
            <div className="absolute top-0 left-1/2 h-full w-px bg-baseline" />
            <div
              className={`absolute top-0 h-full rounded-full ${s.net_pnl >= 0 ? 'bg-pos' : 'bg-neg'}`}
              style={s.net_pnl >= 0 ? { left: '50%', width: `${(Math.abs(s.net_pnl) / max) * 50}%` } : { right: '50%', width: `${(Math.abs(s.net_pnl) / max) * 50}%` }}
            />
          </div>
          <span className="num w-14 shrink-0 text-right text-ink-2">{compactMoney(s.net_pnl)}</span>
        </div>
      ))}
    </div>
  )
}

export function InstrumentsPage() {
  const { params, label } = usePeriod()
  const { data, isLoading, error } = useQuery({ queryKey: ['instruments', params], queryFn: () => api.instruments(params) })
  return (
    <>
      <PageHeader title="Instruments" sub={`What works and what leaks money, per instrument · ${label}`}>
        <PeriodPicker />
      </PageHeader>
      {isLoading && <Spinner />}
      {error && <ErrorBox error={error} />}
      {data && data.length === 0 && <Empty title="No closed trades in this period" />}
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data?.map((i) => (
          <Link key={i.instrument} to={`/instruments/${i.instrument}`} className="block rounded-2xl border border-border bg-gradient-to-b from-surface-2/70 to-surface p-5 shadow-[inset_0_1px_0_0_rgb(255_255_255/0.04)] transition hover:-translate-y-0.5 hover:border-accent/40 hover:shadow-lg hover:shadow-black/30">
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-lg font-semibold">{i.instrument}</div>
                <div className="text-xs text-muted">{i.stats.trades} trades</div>
              </div>
              <div className="text-right">
                <Pnl value={i.stats.net_pnl} className="text-lg font-semibold" />
                <div className="mt-0.5">
                  <VerdictBadge verdict={i.verdict} />
                </div>
              </div>
            </div>
            <dl className="mt-3 grid grid-cols-4 gap-2 text-center">
              {[
                ['Win rate', pct(i.stats.win_rate)],
                ['PF', ratio(i.stats.profit_factor)],
                ['Expect.', compactMoney(i.stats.expectancy ?? 0)],
                ['Avg R', rMult(i.stats.avg_r)],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl bg-surface-3/50 py-2 ring-1 ring-white/[0.04]">
                  <dt className="text-[10px] text-muted uppercase">{k}</dt>
                  <dd className="num text-sm">{v}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-3">
              <SessionStrip sessions={i.sessions} />
            </div>
            <ul className="mt-2 border-t border-border pt-1">
              {i.insights.slice(1, 3).map((ins, n) => (
                <InsightRow key={n} insight={ins} />
              ))}
            </ul>
            {i.flags.length > 0 && (
              <div className="mt-2 flex items-center gap-1.5 text-xs text-warn">
                <AlertTriangle size={12} aria-hidden /> {i.flags.length} red flag{i.flags.length > 1 && 's'}: {i.flags[0].title}
              </div>
            )}
          </Link>
        ))}
      </div>
    </>
  )
}
