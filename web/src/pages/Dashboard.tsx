import { keepPreviousData, useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  ArrowRight,
  BadgeCheck,
  CalendarDays,
  CheckCircle2,
  Clock,
  Crosshair,
  Flag,
  Landmark,
  Layers,
  LineChart,
  Scale,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { BalanceChart, BreakdownBars, DailyBars, EquityChart, Sparkline, WinRing } from '../components/charts'
import { Card, Delta, Empty, ErrorBox, InsightRow, PageHeader, PeriodPicker, Pnl, SeverityBadge, Skeleton, Stat } from '../components/ui'
import { api } from '../lib/api'
import { ago, currency, dt, minutes, money, pct, pnlClass, ratio, rMult } from '../lib/format'
import { usePeriod } from '../lib/period'
import type { Dashboard } from '../lib/types'

const signedRatio = (d: number) => `${d > 0 ? '+' : '−'}${Math.abs(d).toFixed(2)}`

function DashboardSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <Skeleton className="h-52 lg:col-span-2" />
        <Skeleton className="h-52" />
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-80" />
    </div>
  )
}

function AccountHero({ data, className }: { data: Dashboard; className?: string }) {
  const total = data.account.total
  if (!total) {
    return (
      <Card title="Account balance" icon={Landmark} className={className}>
        <p className="text-sm text-muted">
          Your balance appears here once the TradeJournalSync EA reports from MT5. <Link to="/settings" className="text-accent hover:underline">Set it up</Link>
        </p>
      </Card>
    )
  }
  const ccy = total.currency
  const main = data.account.accounts.find((a) => a.currency === ccy)
  const metrics = [
    { label: 'Equity', value: currency(total.equity, ccy), tone: undefined },
    { label: 'Open P&L', value: money(total.floating), tone: pnlClass(total.floating) },
    { label: 'Today', value: money(data.today.net_pnl), tone: pnlClass(data.today.net_pnl), sub: `${data.today.trades} closed` },
    {
      label: 'All-time return',
      value: total.return_pct === null ? '—' : `${total.return_pct > 0 ? '+' : total.return_pct < 0 ? '−' : ''}${Math.abs(total.return_pct * 100).toFixed(2)}%`,
      tone: pnlClass(total.return_pct),
      sub: money(total.trading_pnl),
    },
  ]
  return (
    <section
      className={clsx(
        'relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-accent/[0.14] via-surface-2/80 to-surface p-5 shadow-[inset_0_1px_0_0_rgb(255_255_255/0.05)]',
        className,
      )}
    >
      <div className="pointer-events-none absolute -top-24 -right-24 size-72 rounded-full bg-accent/10 blur-3xl" aria-hidden />
      <div className="relative flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <span className="grid size-10 place-items-center rounded-xl bg-accent/15 text-accent ring-1 ring-accent/25">
            <Wallet size={18} aria-hidden />
          </span>
          <div>
            <div className="text-sm font-medium text-ink-2">Account balance</div>
            <div className="text-xs text-muted">
              {main ? `${main.broker ?? 'MT5'} · ${main.login}` : `${total.accounts} accounts`}
              {main?.trade_mode && ` · ${main.trade_mode}`}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted">
          {total.reconciled && (
            <span className="inline-flex items-center gap-1 rounded-full bg-pos/12 px-2 py-0.5 font-medium text-pos ring-1 ring-pos/20" title="The journal's own calculation lands exactly on the balance MT5 reports">
              <BadgeCheck size={13} aria-hidden /> Matches MT5
            </span>
          )}
          <span className="inline-flex items-center gap-1">
            <Clock size={12} aria-hidden /> {ago(total.as_of)}
          </span>
        </div>
      </div>

      <div className="relative mt-4 grid items-end gap-4 md:grid-cols-[auto_minmax(0,1fr)]">
        <div>
          <div className="num text-4xl font-semibold tracking-tight sm:text-[2.75rem]">{currency(total.balance, ccy)}</div>
          <div className="mt-1 text-xs text-muted">
            Deposited {currency(total.deposits, ccy)}
            {total.withdrawals > 0 && ` · withdrawn ${currency(total.withdrawals, ccy)}`}
          </div>
        </div>
        <div className="min-w-0 md:pl-6" aria-label="Balance over the selected range">
          <Sparkline data={data.balance} />
        </div>
      </div>

      <dl className="relative mt-4 grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-border bg-border sm:grid-cols-4">
        {metrics.map((m) => (
          <div key={m.label} className="bg-surface/80 px-3.5 py-2.5 backdrop-blur">
            <dt className="text-[11px] font-medium text-muted">{m.label}</dt>
            <dd className={clsx('num mt-0.5 text-sm font-semibold', m.tone)}>
              {m.value}
              {m.sub && <span className="ml-1.5 text-xs font-normal text-muted">{m.sub}</span>}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}

function WinLossCard({ data }: { data: Dashboard }) {
  const s = data.summary
  const maxLeg = Math.max(Math.abs(s.avg_win ?? 0), Math.abs(s.avg_loss ?? 0), 1)
  return (
    <Card title="Wins & losses" icon={Target}>
      <div className="flex items-center gap-5">
        <WinRing summary={s} />
        <ul className="space-y-2 text-sm">
          {[
            ['Wins', s.wins, 'bg-pos'],
            ['Losses', s.losses, 'bg-neg'],
            ['Breakeven', s.breakeven, 'bg-muted'],
          ].map(([label, n, dot]) => (
            <li key={label as string} className="flex items-center gap-2">
              <span className={clsx('size-2.5 rounded-full', dot as string)} aria-hidden />
              <span className="text-ink-2">{label}</span>
              <span className="num ml-auto pl-4 font-semibold">{n}</span>
            </li>
          ))}
          <li className="pt-1 text-xs text-muted">
            Streaks: {s.max_consecutive_wins}W / {s.max_consecutive_losses}L
          </li>
        </ul>
      </div>
      <div className="mt-4 space-y-2">
        {[
          ['Avg win', s.avg_win, 'bg-pos'],
          ['Avg loss', s.avg_loss, 'bg-neg'],
        ].map(([label, v, bar]) => (
          <div key={label as string} className="grid grid-cols-[4.5rem_minmax(0,1fr)_4.5rem] items-center gap-2 text-xs">
            <span className="text-muted">{label}</span>
            <div className="h-2 rounded-full bg-surface-3" aria-hidden>
              <div className={clsx('h-full rounded-full', bar as string)} style={{ width: `${(Math.abs((v as number) ?? 0) / maxLeg) * 100}%` }} />
            </div>
            <span className="num text-right text-ink-2">{money(v as number | null)}</span>
          </div>
        ))}
        <div className="text-xs text-muted">
          Payoff ratio <span className="num text-ink-2">{ratio(s.payoff_ratio)}</span>
          {s.payoff_ratio !== null && s.payoff_ratio > 0 && (
            <> · breakeven win rate <span className="num text-ink-2">{pct(1 / (1 + s.payoff_ratio))}</span></>
          )}
        </div>
      </div>
    </Card>
  )
}

export function DashboardPage() {
  const { params, label } = usePeriod()
  const [view, setView] = useState<'balance' | 'pnl'>('balance')
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ['dashboard', params],
    queryFn: () => api.dashboard(params),
    placeholderData: keepPreviousData,
  })
  const prev = data?.previous ?? null
  const s = data?.summary
  const ccy = data?.account.total?.currency ?? 'USD'
  const showBalance = view === 'balance' && !!data?.account.total

  return (
    <>
      <PageHeader
        title="Dashboard"
        sub={
          <span className={clsx('transition-opacity', isFetching && 'opacity-60')}>
            {label}
            {data && ` · ${data.summary.trades} closed trades · ${data.open_trades} open`}
          </span>
        }
      >
        <PeriodPicker />
      </PageHeader>
      {isLoading && <DashboardSkeleton />}
      {error && <ErrorBox error={error} />}
      {data && s && (
        <div className="space-y-4">
          <div className="grid gap-4 lg:grid-cols-3">
            <AccountHero data={data} className="lg:col-span-2" />
            <WinLossCard data={data} />
          </div>

          {s.trades === 0 ? (
            <Empty title="No closed trades in this range" icon={CalendarDays}>
              Pick a longer range, or check that the TradeJournalSync EA is running in MT5.
            </Empty>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                <Stat
                  label="Net P&L"
                  icon={TrendingUp}
                  value={<Pnl value={s.net_pnl} />}
                  delta={<Delta value={s.net_pnl} previous={prev?.net_pnl} format={money} />}
                  sub={prev ? 'vs previous' : `${money(s.gross_profit)} / ${money(s.gross_loss)}`}
                />
                <Stat
                  label="Profit factor"
                  icon={Scale}
                  value={ratio(s.profit_factor)}
                  delta={<Delta value={s.profit_factor} previous={prev?.profit_factor} format={signedRatio} />}
                  sub={`Payoff ${ratio(s.payoff_ratio)}`}
                />
                <Stat
                  label="Expectancy"
                  icon={Crosshair}
                  value={<span className={pnlClass(s.expectancy)}>{money(s.expectancy)}</span>}
                  delta={<Delta value={s.expectancy} previous={prev?.expectancy} format={money} />}
                  sub="per trade"
                />
                <Stat
                  label="Avg R"
                  icon={Layers}
                  value={<span className={pnlClass(s.avg_r)}>{rMult(s.avg_r)}</span>}
                  delta={<Delta value={s.avg_r} previous={prev?.avg_r} format={rMult} />}
                  sub={`${s.trades_with_r} of ${s.trades} with a stop`}
                />
                <Stat
                  label="Max drawdown"
                  icon={TrendingDown}
                  value={<span className="text-neg">{money(-s.max_drawdown)}</span>}
                  delta={<Delta value={s.max_drawdown} previous={prev?.max_drawdown} format={money} better="down" />}
                  sub={`Worst streak ${s.max_consecutive_losses}L`}
                />
              </div>

              <div className="grid gap-4 lg:grid-cols-3">
                <Card
                  title={showBalance ? 'Account balance' : 'Cumulative P&L'}
                  icon={LineChart}
                  className="lg:col-span-2"
                  action={
                    data.account.total && (
                      <div role="radiogroup" aria-label="Chart" className="flex rounded-lg border border-border bg-surface p-0.5 text-xs">
                        {(
                          [
                            ['balance', 'Balance'],
                            ['pnl', 'P&L'],
                          ] as const
                        ).map(([k, l]) => (
                          <button
                            key={k}
                            role="radio"
                            aria-checked={view === k}
                            onClick={() => setView(k)}
                            className={clsx('h-6 rounded-md px-2.5 font-medium', view === k ? 'bg-surface-3 text-ink' : 'text-muted hover:text-ink')}
                          >
                            {l}
                          </button>
                        ))}
                      </div>
                    )
                  }
                >
                  {showBalance ? <BalanceChart data={data.balance} ccy={ccy} /> : <EquityChart data={data.equity} height={260} />}
                </Card>
                <Card title="Net P&L by instrument" icon={Layers} action={<Link to="/instruments" className="text-xs text-accent hover:underline">Details</Link>}>
                  <BreakdownBars data={data.by_instrument} />
                </Card>
              </div>

              <div className="grid gap-4 lg:grid-cols-3">
                <Card title="Daily P&L" icon={CalendarDays} className="lg:col-span-2" action={<Link to="/calendar" className="text-xs text-accent hover:underline">Calendar</Link>}>
                  <DailyBars data={data.daily} />
                </Card>
                <Card title="By session" icon={Clock}>
                  <BreakdownBars data={data.by_session} />
                  <div className="mt-3 border-t border-border pt-3 text-xs text-muted">
                    Avg hold: winners <span className="text-ink-2">{minutes(s.avg_hold_win_min)}</span>, losers <span className="text-ink-2">{minutes(s.avg_hold_loss_min)}</span>
                  </div>
                </Card>
              </div>

              <div className="grid gap-4 lg:grid-cols-3">
                <Card title="What the numbers say" icon={LineChart}>
                  <ul className="-my-1 divide-y divide-border">
                    {data.insights.map((i, n) => (
                      <InsightRow key={n} insight={i} />
                    ))}
                  </ul>
                </Card>
                <Card title="Red flags" icon={Flag}>
                  {data.flags.length === 0 ? (
                    <div className="text-sm text-muted">No behavioural red flags in this range.</div>
                  ) : (
                    <ul className="space-y-3.5">
                      {data.flags.map((f) => (
                        <li key={f.code + f.title}>
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-sm font-medium">{f.title}</span>
                            <SeverityBadge severity={f.severity} />
                          </div>
                          <p className="mt-0.5 text-xs leading-relaxed text-muted">{f.description}</p>
                        </li>
                      ))}
                    </ul>
                  )}
                </Card>
                <Card
                  title="Latest AI coaching"
                  icon={Sparkles}
                  action={
                    data.latest_report && (
                      <Link to={`/coach/${data.latest_report.id}`} className="inline-flex items-center gap-1 text-xs text-accent hover:underline">
                        Open <ArrowRight size={12} />
                      </Link>
                    )
                  }
                >
                  {data.latest_report ? (
                    <>
                      <div className="text-sm font-medium">{data.latest_report.title}</div>
                      <div className="text-xs text-muted">{dt(data.latest_report.created_at, 'd MMM yyyy')}</div>
                      <div className="mt-3 text-[11px] font-semibold tracking-wider text-muted uppercase">Action plan</div>
                      <ul className="mt-1.5 space-y-1.5">
                        {data.latest_report.action_plan.map((a, n) => (
                          <li key={n} className="flex gap-2 text-sm text-ink-2">
                            <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                            {a}
                          </li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <div className="text-sm text-muted">
                      No reviews yet. In Claude Desktop, ask <span className="text-ink-2">“Do my weekly trading review”</span>.{' '}
                      <Link to="/coach" className="text-accent hover:underline">
                        How
                      </Link>
                    </div>
                  )}
                </Card>
              </div>
            </>
          )}
        </div>
      )}
    </>
  )
}
