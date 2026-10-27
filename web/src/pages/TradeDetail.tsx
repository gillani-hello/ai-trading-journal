import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { ArrowLeft, ImagePlus, Sparkles, Star, Trash2 } from 'lucide-react'
import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ExcursionBar } from '../components/charts'
import { TagPicker } from '../components/TagPicker'
import { Badge, Button, Card, ErrorBox, Field, inputCls, Modal, PageHeader, Pnl, SeverityBadge, SideBadge, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { closeReason, dt, duration, money, price, rMult } from '../lib/format'
import type { Journal, TradeDetail } from '../lib/types'

export function TradeDetailPage() {
  const id = Number(useParams().id)
  const { data, isLoading, error } = useQuery({ queryKey: ['trade', id], queryFn: () => api.trade(id) })
  if (isLoading) return <Spinner />
  if (error) return <ErrorBox error={error} />
  if (!data) return null
  return <TradeView trade={data} />
}

function Metric({ label, value, className }: { label: string; value: ReactNode; className?: string }) {
  return (
    <div>
      <dt className="text-xs text-muted">{label}</dt>
      <dd className={clsx('num mt-0.5 text-sm text-ink', className)}>{value}</dd>
    </div>
  )
}

function TradeView({ trade: t }: { trade: TradeDetail }) {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const net = t.status === 'open' ? t.floating_pnl : t.net_pnl
  const del = useMutation({
    mutationFn: () => api.deleteTrade(t.id),
    onSuccess: () => {
      qc.invalidateQueries()
      navigate('/trades')
    },
  })
  const slMoved = t.risk_sl !== null && t.final_sl !== null && t.risk_sl !== t.final_sl
  const slNote =
    t.sl_source === 'entry'
      ? 'on the order'
      : t.sl_source === 'added'
        ? `added ${duration(t.sl_delay_seconds)} after entry`
        : t.sl_source === 'close'
          ? 'not on the order; seen at close'
          : t.final_sl !== null
            ? 'trailed by close; original risk unknown'
            : 'none'

  return (
    <>
      <Link to="/trades" className="mb-3 inline-flex items-center gap-1 text-sm text-muted hover:text-ink">
        <ArrowLeft size={14} /> Trades
      </Link>
      <PageHeader
        title={
          <span className="flex items-center gap-2.5">
            <Link to={`/instruments/${t.instrument}`} className="hover:text-accent">
              {t.instrument}
            </Link>
            <SideBadge direction={t.direction} />
            {t.status === 'open' && <Badge tone="warn">Open</Badge>}
            <Badge>{t.source === 'mt5' ? 'MT5' : 'Manual'}</Badge>
          </span>
        }
        sub={`${dt(t.open_time)} → ${t.close_time ? dt(t.close_time) : 'still open'} · ${t.account.name}`}
      >
        <div className="text-right">
          <Pnl value={net} className="text-2xl font-semibold" />
          <div className="text-sm text-muted">{t.status === 'open' ? 'floating' : rMult(t.r_multiple)}</div>
        </div>
      </PageHeader>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card title="Execution">
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
              <Metric label="Entry" value={price(t.entry_price)} />
              <Metric label="Exit" value={price(t.exit_price)} />
              <Metric label="Size" value={`${t.volume} lots`} />
              <Metric label="Held" value={duration(t.holding_seconds)} />
              <Metric
                label="Stop-loss (1R)"
                value={
                  <>
                    {slMoved ? `${price(t.risk_sl)} → ${price(t.final_sl)}` : price(t.risk_sl ?? t.final_sl)}
                    <span className={clsx('block text-xs', t.sl_source === 'entry' ? 'text-muted' : 'text-warn')}>{slNote}</span>
                  </>
                }
              />
              <Metric label="Take-profit" value={price(t.initial_tp)} />
              <Metric label="Closed by" value={closeReason(t.close_reason)} />
              <Metric label="Session" value={t.session ?? '—'} />
              <Metric label="Gross" value={money(t.gross_pnl)} />
              <Metric label="Commission" value={money(t.commission)} />
              <Metric label="Swap" value={money(t.swap)} />
              <Metric label="Points" value={t.points !== null ? t.points.toFixed(0) : '—'} />
            </dl>
            {t.mfe_points !== null && t.mae_points !== null && t.points !== null && (
              <div className="mt-5">
                <div className="mb-2 text-xs text-muted">Price excursion while open</div>
                <ExcursionBar mae={t.mae_points} mfe={t.mfe_points} result={t.points} />
              </div>
            )}
          </Card>

          <JournalForm trade={t} />
          <Screenshots trade={t} />

          {t.deals.length > 0 && (
            <Card title="MT5 deals">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted">
                      {['Time', 'Deal', 'Type', 'Volume', 'Price', 'SL', 'TP', 'Profit', 'Costs', 'Reason'].map((h) => (
                        <th key={h} className="pb-2 font-medium">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="num text-ink-2">
                    {t.deals.map((d) => (
                      <tr key={d.ticket} className="border-t border-border/60">
                        <td className="py-1.5 pr-3 whitespace-nowrap">{dt(d.time, 'd MMM HH:mm:ss')}</td>
                        <td className="pr-3">#{d.ticket}</td>
                        <td className="pr-3">
                          {d.type} {d.entry}
                        </td>
                        <td className="pr-3">{d.volume}</td>
                        <td className="pr-3">{price(d.price)}</td>
                        <td className="pr-3">{price(d.sl)}</td>
                        <td className="pr-3">{price(d.tp)}</td>
                        <td className="pr-3">
                          <Pnl value={d.profit} />
                        </td>
                        <td className="pr-3">{money(d.commission + d.swap)}</td>
                        <td>{d.reason}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </div>

        <div className="space-y-4">
          <Card title={<span className="inline-flex items-center gap-1.5"><Sparkles size={14} className="text-accent" /> AI feedback</span>}>
            {t.journal.ai_feedback ? (
              <>
                <p className="text-sm leading-relaxed whitespace-pre-line text-ink-2">{t.journal.ai_feedback}</p>
                <div className="mt-2 text-xs text-muted">{dt(t.journal.ai_feedback_at)}</div>
              </>
            ) : (
              <p className="text-sm text-muted">
                Ask Claude to review it: run the <code className="text-ink-2">trade_review</code> prompt with trade id <b className="text-ink">{t.id}</b>, or just say "review trade {t.id}".
              </p>
            )}
          </Card>
          <Card title="Red flags on this trade">
            {t.flags.length === 0 ? (
              <p className="text-sm text-muted">None.</p>
            ) : (
              <ul className="space-y-2">
                {t.flags.map((f) => (
                  <li key={f.code + f.title} className="flex items-center justify-between gap-2 text-sm">
                    {f.title}
                    <SeverityBadge severity={f.severity} />
                  </li>
                ))}
              </ul>
            )}
          </Card>
          {t.source === 'manual' && (
            <Button variant="danger" onClick={() => confirm('Delete this manually logged trade?') && del.mutate()}>
              <Trash2 size={14} /> Delete trade
            </Button>
          )}
        </div>
      </div>
    </>
  )
}

function JournalForm({ trade }: { trade: TradeDetail }) {
  const qc = useQueryClient()
  const { data: tags } = useQuery({ queryKey: ['tags'], queryFn: api.tags })
  const [j, setJ] = useState<Journal>(trade.journal)
  const [dirty, setDirty] = useState(false)
  useEffect(() => {
    setJ(trade.journal)
    setDirty(false)
  }, [trade.journal])
  const update = (patch: Partial<Journal>) => {
    setJ({ ...j, ...patch })
    setDirty(true)
  }
  const save = useMutation({
    mutationFn: () =>
      api.patchJournal(trade.id, {
        setup: j.setup,
        emotions: j.emotions,
        mistakes: j.mistakes,
        notes: j.notes,
        rating: j.rating,
        followed_plan: j.followed_plan,
      }),
    onSuccess: (data) => {
      qc.setQueryData(['trade', trade.id], data)
      qc.invalidateQueries({ queryKey: ['tags'] })
      qc.invalidateQueries({ queryKey: ['trades'] })
      setDirty(false)
    },
  })
  return (
    <Card
      title="Journal"
      action={
        <div className="flex items-center gap-2">
          {save.isSuccess && !dirty && <span className="text-xs text-pos">Saved</span>}
          <Button size="sm" variant="primary" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
            Save
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Setup">
            <input className={inputCls} list="setup-options" value={j.setup ?? ''} onChange={(e) => update({ setup: e.target.value || null })} placeholder="e.g. Pullback" />
            <datalist id="setup-options">
              {tags?.setup.map((s) => (
                <option key={s} value={s} />
              ))}
            </datalist>
          </Field>
          <Field label="Execution rating">
            <div className="flex h-9 items-center gap-1" role="radiogroup" aria-label="Rating">
              {[1, 2, 3, 4, 5].map((n) => (
                <button key={n} type="button" role="radio" aria-checked={j.rating === n} aria-label={`${n} of 5`} onClick={() => update({ rating: j.rating === n ? null : n })}>
                  <Star size={18} className={clsx(j.rating !== null && n <= j.rating ? 'fill-warn text-warn' : 'text-muted')} />
                </button>
              ))}
            </div>
          </Field>
          <Field label="Followed my plan?">
            <select
              className={inputCls}
              value={j.followed_plan === null ? '' : String(j.followed_plan)}
              onChange={(e) => update({ followed_plan: e.target.value === '' ? null : e.target.value === 'true' })}
            >
              <option value="">—</option>
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </Field>
        </div>
        <Field label="Emotions">
          <TagPicker options={tags?.emotion ?? []} value={j.emotions} onChange={(emotions) => update({ emotions })} />
        </Field>
        <Field label="Mistakes">
          <TagPicker options={tags?.mistake ?? []} value={j.mistakes} onChange={(mistakes) => update({ mistakes })} tone="neg" />
        </Field>
        <Field label="Notes">
          <textarea className={inputCls} rows={4} value={j.notes ?? ''} onChange={(e) => update({ notes: e.target.value || null })} placeholder="Why you took it, how you managed it, what you'd do differently…" />
        </Field>
        {save.error && <ErrorBox error={save.error} />}
      </div>
    </Card>
  )
}

function Screenshots({ trade }: { trade: TradeDetail }) {
  const qc = useQueryClient()
  const fileRef = useRef<HTMLInputElement>(null)
  const [zoom, setZoom] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)
  const refresh = () => qc.invalidateQueries({ queryKey: ['trade', trade.id] })
  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const f of files) await api.uploadScreenshot(trade.id, f)
    },
    onSuccess: refresh,
  })
  const remove = useMutation({ mutationFn: (id: number) => api.deleteScreenshot(id), onSuccess: refresh })
  const images = (list: FileList | null | undefined) => Array.from(list ?? []).filter((f) => f.type.startsWith('image/'))
  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const files = images(e.dataTransfer.files)
    if (files.length) upload.mutate(files)
  }
  const onPaste = (e: ClipboardEvent) => {
    const files = images(e.clipboardData.files)
    if (files.length) upload.mutate(files)
  }
  return (
    <Card title="Screenshots">
      <div
        tabIndex={0}
        onPaste={onPaste}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={clsx('rounded-lg outline-none focus-visible:ring-1 focus-visible:ring-accent', dragging && 'ring-1 ring-accent')}
      >
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {trade.screenshots.map((s) => (
            <figure key={s.id} className="group relative overflow-hidden rounded-lg border border-border">
              <button className="block w-full" onClick={() => setZoom(s.url)} aria-label="Enlarge screenshot">
                <img src={s.url} alt={s.caption ?? 'Trade screenshot'} className="aspect-video w-full object-cover" />
              </button>
              <button
                aria-label="Delete screenshot"
                onClick={() => confirm('Delete this screenshot?') && remove.mutate(s.id)}
                className="absolute top-1.5 right-1.5 rounded-md bg-black/60 p-1 text-ink opacity-0 group-hover:opacity-100 focus:opacity-100"
              >
                <Trash2 size={13} />
              </button>
              {s.caption && <figcaption className="px-2 py-1 text-xs text-muted">{s.caption}</figcaption>}
            </figure>
          ))}
          <button
            onClick={() => fileRef.current?.click()}
            className="flex aspect-video flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-border text-xs text-muted hover:border-accent hover:text-ink"
          >
            <ImagePlus size={18} />
            {upload.isPending ? 'Uploading…' : 'Add, drop or paste'}
          </button>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => {
            const files = images(e.target.files)
            if (files.length) upload.mutate(files)
            e.target.value = ''
          }}
        />
      </div>
      {upload.error && <div className="mt-2"><ErrorBox error={upload.error} /></div>}
      <Modal open={zoom !== null} onClose={() => setZoom(null)} title="Screenshot">
        {zoom && <img src={zoom} alt="Trade screenshot" className="w-full rounded-lg" />}
      </Modal>
    </Card>
  )
}
