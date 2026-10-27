import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { CheckCircle2, Trash2 } from 'lucide-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Badge, Button, Card, CopyBlock, ErrorBox, InsightRow, PageHeader, Spinner, VerdictBadge } from '../components/ui'
import { api } from '../lib/api'
import { dt, titleCase } from '../lib/format'
import { usePeriod } from '../lib/period'
import type { Report } from '../lib/types'

function HowTo() {
  return (
    <Card title="Get a review from Claude">
      <div className="space-y-3 text-sm text-ink-2">
        <p>The coach runs in Claude (your subscription, no API key). Claude reads your journal through the trading-journal MCP server, analyses it, and saves the report here.</p>
        <div>
          <div className="mb-1 text-xs text-muted">Claude Code — type the prompt as a slash command:</div>
          <CopyBlock text="/mcp__trading-journal__weekly_review" />
        </div>
        <div>
          <div className="mb-1 text-xs text-muted">Claude Desktop — use + › trading-journal › weekly_review, or simply ask:</div>
          <CopyBlock text="Do my weekly trading review and save it to my journal." />
        </div>
        <p className="text-xs text-muted">
          Also available: <code>monthly_review</code>, <code>instrument_review</code> (pick a symbol), <code>trade_review</code> and <code>log_trades</code>. Set it up under{' '}
          <Link to="/settings" className="text-accent hover:underline">
            Settings
          </Link>
          .
        </p>
      </div>
    </Card>
  )
}

function Section({ title, items, tone }: { title: string; items: string[]; tone: string }) {
  if (!items.length) return null
  return (
    <Card title={<span className={tone}>{title}</span>}>
      <ul className="list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink-2">
        {items.map((x, n) => (
          <li key={n}>{x}</li>
        ))}
      </ul>
    </Card>
  )
}

function ReportView({ report }: { report: Report }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const c = report.content
  const del = useMutation({
    mutationFn: () => api.deleteReport(report.id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports'] })
      navigate('/coach')
    },
  })
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-surface p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <Badge tone="accent">{titleCase(report.kind)}</Badge>
              {report.symbol && <Badge>{report.symbol}</Badge>}
            </div>
            <h2 className="mt-2 text-lg font-semibold">{report.title}</h2>
            <div className="text-xs text-muted">
              {report.period_start && `${dt(report.period_start, 'd MMM')} – ${dt(report.period_end, 'd MMM yyyy')} · `}saved {dt(report.created_at)}
            </div>
          </div>
          <div className="flex items-center gap-3">
            {c.discipline_score !== null && (
              <div className="text-right">
                <div className="text-xs text-muted">Discipline</div>
                <div className="text-2xl font-semibold">
                  {c.discipline_score}
                  <span className="text-sm text-muted">/10</span>
                </div>
              </div>
            )}
            <Button size="sm" variant="ghost" aria-label="Delete report" onClick={() => confirm('Delete this report?') && del.mutate()}>
              <Trash2 size={14} />
            </Button>
          </div>
        </div>
        <p className="mt-4 text-sm leading-relaxed whitespace-pre-line text-ink-2">{c.summary}</p>
        {c.progress_vs_previous && (
          <p className="mt-3 rounded-lg bg-surface-2 p-3 text-sm text-ink-2">
            <span className="font-medium text-ink">Since last review: </span>
            {c.progress_vs_previous}
          </p>
        )}
      </div>

      {c.action_plan.length > 0 && (
        <Card title="Action plan">
          <ul className="space-y-2">
            {c.action_plan.map((a, n) => (
              <li key={n} className="flex gap-2.5 text-sm">
                <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-accent" aria-hidden />
                {a}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid gap-4 md:grid-cols-3">
        <Section title="Strengths" items={c.strengths} tone="text-pos" />
        <Section title="Weaknesses" items={c.weaknesses} tone="text-neg" />
        <Section title="Psychology" items={c.psychology} tone="text-warn" />
      </div>

      {c.instruments.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2">
          {c.instruments.map((s) => (
            <Card
              key={s.symbol}
              title={
                <Link to={`/instruments/${s.symbol}`} className="text-ink hover:text-accent">
                  {s.symbol}
                </Link>
              }
              action={<VerdictBadge verdict={s.verdict} />}
            >
              <p className="text-sm font-medium">{s.headline}</p>
              <div className="mt-3 space-y-3 text-sm">
                {[
                  ['Doing well', s.doing_well, 'text-pos'],
                  ['Going wrong', s.going_wrong, 'text-neg'],
                  ['Improve', s.improvements, 'text-accent'],
                  ['Rules', s.rules, 'text-warn'],
                ].map(([label, items, tone]) =>
                  (items as string[]).length ? (
                    <div key={label as string}>
                      <div className={clsx('text-xs font-medium tracking-wide uppercase', tone as string)}>{label as string}</div>
                      <ul className="mt-1 list-disc space-y-1 pl-5 text-ink-2">
                        {(items as string[]).map((x, n) => (
                          <li key={n}>{x}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null,
                )}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  )
}

export function CoachPage() {
  const params = useParams()
  const { params: range } = usePeriod()
  const { data: list, isLoading, error } = useQuery({ queryKey: ['reports'], queryFn: () => api.reports() })
  const selectedId = params.id ? Number(params.id) : list?.[0]?.id
  const { data: report, isLoading: loadingReport } = useQuery({
    queryKey: ['report', selectedId],
    queryFn: () => api.report(selectedId!),
    enabled: selectedId !== undefined,
  })
  const { data: insights } = useQuery({ queryKey: ['insights', range], queryFn: () => api.insights(range) })

  return (
    <>
      <PageHeader title="AI Coach" sub="Reviews written by Claude from your journal" />
      {isLoading && <Spinner />}
      {error && <ErrorBox error={error} />}
      <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div className="space-y-4">
          <Card title="Reviews">
            {list && list.length === 0 && <p className="text-sm text-muted">None yet.</p>}
            <ul className="-mx-2 space-y-0.5">
              {list?.map((r) => (
                <li key={r.id}>
                  <Link
                    to={`/coach/${r.id}`}
                    className={clsx('block rounded-lg px-2 py-2 hover:bg-surface-2', r.id === selectedId && 'bg-surface-3')}
                  >
                    <div className="truncate text-sm font-medium">{r.title}</div>
                    <div className="text-xs text-muted">
                      {titleCase(r.kind)}
                      {r.symbol && ` · ${r.symbol}`} · {dt(r.created_at, 'd MMM yyyy')}
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
          {insights && insights.length > 0 && (
            <Card title="Instant insights (no AI)">
              <ul className="divide-y divide-border">
                {insights.slice(0, 6).map((i, n) => (
                  <InsightRow key={n} insight={i} />
                ))}
              </ul>
            </Card>
          )}
        </div>
        <div className="space-y-4">
          {loadingReport && <Spinner />}
          {report && <ReportView report={report} />}
          <HowTo />
        </div>
      </div>
    </>
  )
}
