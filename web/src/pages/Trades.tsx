import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus, Search } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { TagPicker } from '../components/TagPicker'
import { TradeTable } from '../components/TradeTable'
import { Button, compactInputCls, Empty, ErrorBox, Field, inputCls, Modal, PageHeader, PeriodPicker, Pnl, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { usePeriod } from '../lib/period'

const PAGE = 50

const FILTERS = ['instrument', 'direction', 'outcome', 'status', 'setup', 'emotion', 'mistake', 'source', 'session', 'q'] as const

export function TradesPage() {
  const { params: range, label } = usePeriod()
  const [params, setParams] = useSearchParams()
  const [logOpen, setLogOpen] = useState(false)
  const sort = params.get('sort') ?? '-time'
  const page = Number(params.get('page') ?? 0)
  const filters = Object.fromEntries(FILTERS.map((k) => [k, params.get(k) ?? (k === 'status' ? 'all' : '')]))

  const set = (k: string, v: string) => {
    const next = new URLSearchParams(params)
    if (v) next.set(k, v)
    else next.delete(k)
    if (k !== 'page') next.delete('page')
    setParams(next, { replace: true })
  }

  const query = { ...range, sort, limit: PAGE, offset: page * PAGE, ...filters }
  const { data, isLoading, error, isFetching } = useQuery({
    queryKey: ['trades', query],
    queryFn: () => api.trades(query),
    placeholderData: keepPreviousData,
  })
  const { data: tags } = useQuery({ queryKey: ['tags'], queryFn: api.tags })
  const { data: instruments } = useQuery({ queryKey: ['instruments', 'all'], queryFn: () => api.instruments({ period: 'all' }) })
  const pageNet = data?.items.reduce((s, t) => s + (t.status === 'closed' ? t.net_pnl : 0), 0) ?? 0

  const select = (k: string, label: string, options: (string | [string, string])[]) => (
    <select aria-label={label} className={`${compactInputCls} py-1.5`} value={filters[k]} onChange={(e) => set(k, e.target.value)}>
      <option value={k === 'status' ? 'all' : ''}>{label}</option>
      {options.map((o) => {
        const [value, text] = Array.isArray(o) ? o : [o, o]
        return (
          <option key={value} value={value}>
            {text}
          </option>
        )
      })}
    </select>
  )

  return (
    <>
      <PageHeader title="Trades" sub={data ? `${data.total} trades · ${label}${isFetching ? ' · updating…' : ''}` : label}>
        <PeriodPicker />
        <Button variant="primary" onClick={() => setLogOpen(true)}>
          <Plus size={15} /> Log trade
        </Button>
      </PageHeader>

      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search size={14} className="absolute top-1/2 left-2.5 -translate-y-1/2 text-muted" />
          <input
            aria-label="Search notes"
            className={`${compactInputCls} w-52 py-1.5 pl-8`}
            placeholder="Search notes, setup…"
            defaultValue={filters.q}
            onKeyDown={(e) => e.key === 'Enter' && set('q', (e.target as HTMLInputElement).value)}
          />
        </div>
        {select('instrument', 'All instruments', instruments?.map((i) => i.instrument) ?? [])}
        {select('direction', 'Both sides', [['long', 'Long'], ['short', 'Short']])}
        {select('outcome', 'Wins & losses', [['win', 'Winners'], ['loss', 'Losers'], ['breakeven', 'Breakeven']])}
        {select('status', 'Open & closed', [['closed', 'Closed'], ['open', 'Open']])}
        {select('session', 'All sessions', ['Asia', 'London', 'Overlap', 'New York'])}
        {select('setup', 'All setups', tags?.setup ?? [])}
        {select('emotion', 'Any emotion', tags?.emotion ?? [])}
        {select('mistake', 'Any mistake', tags?.mistake ?? [])}
        {select('source', 'MT5 & manual', [['mt5', 'MT5'], ['manual', 'Manual']])}
        {FILTERS.some((k) => params.get(k)) && (
          <Button variant="ghost" size="sm" onClick={() => setParams({}, { replace: true })}>
            Clear filters
          </Button>
        )}
      </div>

      {isLoading && <Spinner />}
      {error && <ErrorBox error={error} />}
      {data && data.items.length === 0 && <Empty title="No trades match these filters" />}
      {data && data.items.length > 0 && (
        <>
          <TradeTable trades={data.items} sort={sort} onSort={(s) => set('sort', s)} />
          <div className="mt-3 flex items-center justify-between text-sm text-muted">
            <span>
              Showing {page * PAGE + 1}–{page * PAGE + data.items.length} of {data.total} · closed P&L on this page <Pnl value={pageNet} />
            </span>
            <div className="flex gap-2">
              <Button size="sm" disabled={page === 0} onClick={() => set('page', String(page - 1))}>
                Previous
              </Button>
              <Button size="sm" disabled={(page + 1) * PAGE >= data.total} onClick={() => set('page', String(page + 1))}>
                Next
              </Button>
            </div>
          </div>
        </>
      )}
      {logOpen && <LogTradeModal open onClose={() => setLogOpen(false)} />}
    </>
  )
}

function LogTradeModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { data: tags } = useQuery({ queryKey: ['tags'], queryFn: api.tags })
  const [form, setForm] = useState<Record<string, string>>({ direction: 'long' })
  const [emotions, setEmotions] = useState<string[]>([])
  const [mistakes, setMistakes] = useState<string[]>([])
  const [warnings, setWarnings] = useState<string[]>([])
  const num = (k: string) => (form[k] ? Number(form[k]) : null)
  const create = useMutation({
    mutationFn: () =>
      api.createTrade({
        symbol: form.symbol,
        direction: form.direction,
        entry_price: Number(form.entry_price),
        exit_price: num('exit_price'),
        volume: num('volume'),
        stop_loss: num('stop_loss'),
        take_profit: num('take_profit'),
        pnl: num('pnl'),
        commission: num('commission') ?? 0,
        open_time: form.open_time || null,
        close_time: form.close_time || null,
        setup: form.setup || null,
        notes: form.notes || null,
        emotions,
        mistakes,
      }),
    onSuccess: (res) => {
      qc.invalidateQueries()
      if (res.warnings.length) setWarnings(res.warnings)
      else {
        onClose()
        navigate(`/trades/${res.trade.id}`)
      }
    },
  })
  const input = (k: string, label: string, type = 'number', extra: Record<string, string> = {}) => (
    <Field label={label}>
      <input className={inputCls} type={type} step="any" value={form[k] ?? ''} onChange={(e) => setForm({ ...form, [k]: e.target.value })} {...extra} />
    </Field>
  )
  const submit = (e: FormEvent) => {
    e.preventDefault()
    create.mutate()
  }
  return (
    <Modal open={open} onClose={onClose} title="Log a trade manually">
      <p className="mb-4 text-sm text-muted">
        For trades MT5 doesn't know about. MT5 trades sync automatically — add notes to them from the trade page instead.
      </p>
      <form onSubmit={submit} className="space-y-3">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {input('symbol', 'Instrument', 'text', { required: 'true', placeholder: 'EURUSD' })}
          <Field label="Side">
            <select className={inputCls} value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}>
              <option value="long">Long</option>
              <option value="short">Short</option>
            </select>
          </Field>
          {input('volume', 'Lots')}
          {input('pnl', 'P&L (money)')}
          {input('entry_price', 'Entry', 'number', { required: 'true' })}
          {input('exit_price', 'Exit')}
          {input('stop_loss', 'Stop-loss')}
          {input('take_profit', 'Take-profit')}
          <div className="col-span-2">{input('open_time', 'Opened', 'datetime-local')}</div>
          <div className="col-span-2">{input('close_time', 'Closed', 'datetime-local')}</div>
        </div>
        <Field label="Setup">
          <input className={inputCls} list="setups" value={form.setup ?? ''} onChange={(e) => setForm({ ...form, setup: e.target.value })} />
          <datalist id="setups">
            {tags?.setup.map((s) => (
              <option key={s} value={s} />
            ))}
          </datalist>
        </Field>
        <Field label="Emotions">
          <TagPicker options={tags?.emotion ?? []} value={emotions} onChange={setEmotions} />
        </Field>
        <Field label="Mistakes">
          <TagPicker options={tags?.mistake ?? []} value={mistakes} onChange={setMistakes} tone="neg" />
        </Field>
        <Field label="Notes">
          <textarea className={inputCls} rows={3} value={form.notes ?? ''} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
        </Field>
        {create.error && <ErrorBox error={create.error} />}
        {warnings.length > 0 && (
          <div className="rounded-lg border border-warn/40 bg-warn/10 p-3 text-sm text-warn">
            Saved, with notes:
            <ul className="mt-1 list-disc pl-5">
              {warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" onClick={onClose}>
            {warnings.length ? 'Close' : 'Cancel'}
          </Button>
          {!warnings.length && (
            <Button variant="primary" type="submit" disabled={create.isPending}>
              Save trade
            </Button>
          )}
        </div>
      </form>
    </Modal>
  )
}
