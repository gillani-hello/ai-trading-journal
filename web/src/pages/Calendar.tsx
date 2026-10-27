import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { addMonths, format, parseISO } from 'date-fns'
import { ChevronLeft, ChevronRight, NotebookPen } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Drawer, ErrorBox, Field, inputCls, PageHeader, Pnl, SideBadge, Spinner, Stat } from '../components/ui'
import { api } from '../lib/api'
import { dt, money, pct, rMult } from '../lib/format'
import type { CalendarDay, DayNote } from '../lib/types'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function cellStyle(day: CalendarDay, max: number) {
  if (!day.trades || max <= 0) return undefined
  // Diverging fill: intensity by size of the day, hue by sign (the signed value is always printed too).
  const a = 0.14 + 0.4 * Math.min(Math.abs(day.net_pnl) / max, 1)
  return { backgroundColor: day.net_pnl >= 0 ? `rgb(12 163 12 / ${a})` : `rgb(230 103 103 / ${a})` }
}

export function CalendarPage() {
  const [month, setMonth] = useState(() => format(new Date(), 'yyyy-MM'))
  const [selected, setSelected] = useState<string | null>(null)
  const { data, isLoading, error } = useQuery({ queryKey: ['calendar', month], queryFn: () => api.calendar(month) })
  const shift = (n: number) => setMonth(format(addMonths(parseISO(`${month}-01`), n), 'yyyy-MM'))

  return (
    <>
      <PageHeader title="Calendar" sub={data ? `Days by close time · ${data.timezone}` : undefined}>
        <div className="flex items-center gap-1">
          <Button variant="ghost" aria-label="Previous month" onClick={() => shift(-1)}>
            <ChevronLeft size={16} />
          </Button>
          <div className="w-36 text-center font-medium">{format(parseISO(`${month}-01`), 'MMMM yyyy')}</div>
          <Button variant="ghost" aria-label="Next month" onClick={() => shift(1)}>
            <ChevronRight size={16} />
          </Button>
          <Button size="sm" onClick={() => setMonth(format(new Date(), 'yyyy-MM'))}>
            Today
          </Button>
        </div>
      </PageHeader>
      {isLoading && <Spinner />}
      {error && <ErrorBox error={error} />}
      {data && (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-5">
            <Stat label="Month net" value={<Pnl value={data.summary.net_pnl} />} sub={`${data.summary.trades} trades`} />
            <Stat label="Win rate" value={pct(data.summary.win_rate)} sub={`PF ${data.summary.profit_factor?.toFixed(2) ?? '—'}`} />
            <Stat label="Green / red days" value={`${data.green_days} / ${data.red_days}`} sub={`${data.trading_days} trading days`} />
            <Stat label="Best day" value={<Pnl value={data.best_day?.net_pnl} />} sub={data.best_day ? dt(data.best_day.date, 'EEE d MMM') : undefined} />
            <Stat label="Worst day" value={<Pnl value={data.worst_day?.net_pnl} />} sub={data.worst_day ? dt(data.worst_day.date, 'EEE d MMM') : undefined} />
          </div>

          <div className="overflow-x-auto rounded-2xl border border-border bg-gradient-to-b from-surface-2/60 to-surface p-3 shadow-[inset_0_1px_0_0_rgb(255_255_255/0.04)]">
            <div className="grid min-w-[760px] grid-cols-[repeat(7,minmax(0,1fr))_120px] gap-1.5">
              {[...WEEKDAYS, 'Week'].map((d) => (
                <div key={d} className="px-2 pb-1 text-[11px] font-semibold tracking-wider text-muted uppercase">
                  {d}
                </div>
              ))}
              {data.weeks.map((w) => (
                <div key={w.week_start} className="contents">
                  {w.days.map((day) => {
                    const isToday = day.date === format(new Date(), 'yyyy-MM-dd')
                    return (
                      <button
                        key={day.date}
                        onClick={() => setSelected(day.date)}
                        style={day.in_month ? cellStyle(day, data.max_abs_day) : undefined}
                        className={clsx(
                          'group relative h-24 rounded-xl p-2.5 text-left ring-1 ring-white/[0.04] transition hover:-translate-y-px hover:ring-accent/60 focus-visible:ring-2 focus-visible:ring-accent focus-visible:outline-none',
                          day.trades === 0 && 'bg-surface-2/40',
                          !day.in_month && 'opacity-30',
                          isToday && 'ring-2 ring-accent/80',
                        )}
                      >
                        <div className="flex items-center justify-between text-xs text-muted">
                          <span className={clsx('font-medium', isToday ? 'text-accent' : day.trades ? 'text-ink-2' : undefined)}>{parseISO(day.date).getDate()}</span>
                          {day.has_note && <NotebookPen size={12} aria-label="Has notes" />}
                        </div>
                        {day.trades > 0 && (
                          <div className="mt-2">
                            <div className="num text-[15px] font-semibold text-ink">{money(day.net_pnl, { decimals: Math.abs(day.net_pnl) >= 100 ? 0 : 2 })}</div>
                            <div className="text-[11px] text-ink-2/90">
                              {day.trades} trade{day.trades > 1 && 's'} · {pct(day.win_rate)}
                            </div>
                          </div>
                        )}
                      </button>
                    )
                  })}
                  <div className="flex h-24 flex-col justify-center rounded-xl bg-surface-3/40 px-3 ring-1 ring-white/[0.04]">
                    <div className="text-[10px] font-semibold tracking-wider text-muted uppercase">Week</div>
                    <Pnl value={w.net_pnl} className="text-sm font-semibold" />
                    <div className="text-[11px] text-muted">
                      {w.trades} trades · {w.trading_days}d
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <p className="mt-2 text-xs text-muted">Cell shade grows with the size of the day's result: green for profit, red for loss. Click a day for its trades and notes.</p>
        </>
      )}
      <Drawer open={selected !== null} onClose={() => setSelected(null)} title={selected ? format(parseISO(selected), 'EEEE d MMMM yyyy') : ''}>
        {selected && <DayPanel date={selected} />}
      </Drawer>
    </>
  )
}

function DayPanel({ date }: { date: string }) {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['day', date], queryFn: () => api.day(date) })
  const [note, setNote] = useState<Partial<DayNote>>({})
  useEffect(() => {
    if (data) setNote(data.note)
  }, [data])
  const save = useMutation({
    mutationFn: () =>
      api.putDayNote(date, {
        pre_session_plan: note.pre_session_plan ?? null,
        post_session_review: note.post_session_review ?? null,
        mood: note.mood ?? null,
        rules_followed: note.rules_followed ?? null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['day', date] })
      qc.invalidateQueries({ queryKey: ['calendar'] })
    },
  })
  if (isLoading || !data) return <Spinner />
  const s = data.summary
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Net" value={<Pnl value={s.net_pnl} />} />
        <Stat label="Trades" value={s.trades} sub={`${s.wins}W · ${s.losses}L`} />
        <Stat label="Avg R" value={rMult(s.avg_r)} />
      </div>

      <Card title="Trades">
        {data.trades.length === 0 ? (
          <div className="text-sm text-muted">No trades closed this day.</div>
        ) : (
          <ul className="divide-y divide-border">
            {data.trades.map((t) => (
              <li key={t.id}>
                <Link to={`/trades/${t.id}`} className="flex items-center gap-3 py-2 text-sm hover:text-accent">
                  <span className="w-12 text-xs text-muted">{dt(t.close_time ?? t.open_time, 'HH:mm')}</span>
                  <span className="w-20 font-medium">{t.instrument}</span>
                  <SideBadge direction={t.direction} />
                  <span className="truncate text-xs text-muted">{t.journal.setup}</span>
                  <span className="ml-auto text-right">
                    <Pnl value={t.status === 'open' ? t.floating_pnl : t.net_pnl} />
                    <span className="ml-2 text-xs text-muted">{rMult(t.r_multiple)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Day journal">
        <div className="space-y-3">
          <Field label="Pre-session plan">
            <textarea className={inputCls} rows={3} value={note.pre_session_plan ?? ''} onChange={(e) => setNote({ ...note, pre_session_plan: e.target.value })} placeholder="Levels, bias, which setups you'll take…" />
          </Field>
          <Field label="Post-session review">
            <textarea className={inputCls} rows={4} value={note.post_session_review ?? ''} onChange={(e) => setNote({ ...note, post_session_review: e.target.value })} placeholder="What went well, what didn't, lessons…" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Mood">
              <input className={inputCls} value={note.mood ?? ''} onChange={(e) => setNote({ ...note, mood: e.target.value })} placeholder="focused, tired…" />
            </Field>
            <Field label="Followed my rules?">
              <select
                className={inputCls}
                value={note.rules_followed === null || note.rules_followed === undefined ? '' : String(note.rules_followed)}
                onChange={(e) => setNote({ ...note, rules_followed: e.target.value === '' ? null : e.target.value === 'true' })}
              >
                <option value="">—</option>
                <option value="true">Yes</option>
                <option value="false">No</option>
              </select>
            </Field>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="primary" onClick={() => save.mutate()} disabled={save.isPending}>
              Save notes
            </Button>
            {save.isSuccess && <span className="text-xs text-pos">Saved</span>}
            {save.error && <span className="text-xs text-neg">{(save.error as Error).message}</span>}
          </div>
        </div>
      </Card>
      <p className="text-xs text-muted">Tip: tell Claude "add to today's review: …" and it saves here.</p>
    </div>
  )
}
