import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { RefreshCw, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Badge, Button, Card, CopyBlock, ErrorBox, Field, inputCls, PageHeader, Spinner } from '../components/ui'
import { api } from '../lib/api'
import { ago, money } from '../lib/format'
import type { SessionDef, Settings, Tags } from '../lib/types'

function Mt5Card() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['status'], queryFn: api.status, refetchInterval: 10_000 })
  const sync = useMutation({ mutationFn: (force: boolean) => api.sync(force), onSuccess: () => qc.invalidateQueries() })
  if (!data) return <Spinner />
  const mt5 = data.accounts.filter((a) => a.source === 'mt5')
  return (
    <Card title="MetaTrader 5 connection">
      <div className="space-y-4 text-sm">
        <div>
          <div className="text-xs text-muted">Export folder</div>
          <div className="mt-0.5 flex items-center gap-2 break-all text-ink-2">
            {data.mt5_folder ?? 'MT5 for Mac not found'}
            {data.mt5_folder && <Badge tone={data.mt5_folder_exists ? 'pos' : 'warn'}>{data.mt5_folder_exists ? 'found' : 'not created yet'}</Badge>}
          </div>
        </div>
        {mt5.length > 0 ? (
          <ul className="divide-y divide-border rounded-lg border border-border">
            {mt5.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center justify-between gap-2 p-3">
                <div>
                  <div className="font-medium">{a.name}</div>
                  <div className="text-xs text-muted">
                    {a.server} · {a.trade_mode ?? 'account'} · {a.margin_mode}
                  </div>
                </div>
                <div className="text-right text-xs text-muted">
                  <div className="num text-sm text-ink">
                    {money(a.balance, { sign: false })} {a.currency}
                  </div>
                  EA seen {ago(a.ea_seen_at)} · synced {ago(a.last_sync_at)}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <div className="rounded-lg border border-warn/40 bg-warn/10 p-3 text-warn">No MT5 account has reported yet.</div>
        )}
        {data.last_sync?.message && <p className="text-xs text-muted">{data.last_sync.message}</p>}
        <div className="flex gap-2">
          <Button onClick={() => sync.mutate(false)} disabled={sync.isPending}>
            <RefreshCw size={14} className={sync.isPending ? 'animate-spin' : undefined} /> Sync now
          </Button>
          <Button variant="ghost" onClick={() => sync.mutate(true)} disabled={sync.isPending}>
            Full rebuild
          </Button>
        </div>
        <details className="text-ink-2">
          <summary className="cursor-pointer text-sm text-accent">Set up the EA</summary>
          <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-sm">
            <li>
              In the project folder run <code className="text-ink">uv run tj install-ea</code>. It copies and compiles TradeJournalSync into MT5.
            </li>
            <li>In MT5: Navigator › Expert Advisors › TradeJournal › TradeJournalSync (right-click › Refresh if it's missing).</li>
            <li>Drag it onto any one chart and press OK. It only reads history and never trades, so Algo Trading can stay off.</li>
            <li>Keep that chart open. New fills arrive here within seconds; your full history is imported on first run.</li>
          </ol>
        </details>
      </div>
    </Card>
  )
}

function ClaudeCard() {
  const { data } = useQuery({ queryKey: ['mcp-config'], queryFn: api.mcpConfig })
  if (!data) return null
  return (
    <Card title="Connect Claude (MCP)">
      <div className="space-y-3 text-sm text-ink-2">
        <div>
          <div className="mb-1 text-xs text-muted">Claude Code — run once in a terminal:</div>
          <CopyBlock text={data.claude_code} />
        </div>
        <div>
          <div className="mb-1 text-xs text-muted">
            Claude Desktop — add to <code>{data.claude_desktop_config_path}</code> (or run <code>uv run tj mcp-config --write-desktop</code>), then restart Claude:
          </div>
          <CopyBlock text={JSON.stringify(data.claude_desktop, null, 2)} />
        </div>
        <p className="text-xs text-muted">Prompts: {data.prompts.join(', ')}. Dictate trades by voice in Claude Desktop, or with macOS dictation (press Fn twice).</p>
      </div>
    </Card>
  )
}

function SessionsEditor({ value, onChange }: { value: SessionDef[]; onChange: (v: SessionDef[]) => void }) {
  const set = (i: number, patch: Partial<SessionDef>) => onChange(value.map((s, n) => (n === i ? { ...s, ...patch } : s)))
  return (
    <div className="space-y-2">
      {value.map((s, i) => (
        <div key={i} className="grid grid-cols-[1fr_80px_80px] gap-2">
          <input aria-label="Session name" className={inputCls} value={s.name} onChange={(e) => set(i, { name: e.target.value })} />
          <input aria-label="Start hour UTC" type="number" min={0} max={23} className={inputCls} value={s.start} onChange={(e) => set(i, { start: Number(e.target.value) })} />
          <input aria-label="End hour UTC" type="number" min={0} max={24} className={inputCls} value={s.end} onChange={(e) => set(i, { end: Number(e.target.value) })} />
        </div>
      ))}
      <p className="text-xs text-muted">Name · start hour · end hour, in UTC. A range can wrap past midnight (21 → 7). Applies to trades synced from now on; use Full rebuild to reclassify history.</p>
    </div>
  )
}

function PreferencesCard({ settings }: { settings: Settings }) {
  const qc = useQueryClient()
  const [s, setS] = useState(settings)
  useEffect(() => setS(settings), [settings])
  const { data: zones } = useQuery({ queryKey: ['timezones'], queryFn: api.timezones, staleTime: Infinity })
  const save = useMutation({
    mutationFn: () => api.patchSettings(s),
    onSuccess: (data) => {
      qc.setQueryData(['settings'], data)
      qc.invalidateQueries()
    },
  })
  return (
    <Card
      title="Preferences"
      action={
        <Button size="sm" variant="primary" onClick={() => save.mutate()} disabled={save.isPending}>
          Save
        </Button>
      }
    >
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Display timezone">
            <select className={inputCls} value={s.display_timezone} onChange={(e) => setS({ ...s, display_timezone: e.target.value })}>
              {(zones ?? [s.display_timezone]).map((z) => (
                <option key={z}>{z}</option>
              ))}
            </select>
          </Field>
          <Field label="Broker server time" hint="Auto handles New York-close brokers (UTC+2/+3) across daylight saving.">
            <select className={inputCls} value={s.broker_time_mode} onChange={(e) => setS({ ...s, broker_time_mode: e.target.value as Settings['broker_time_mode'] })}>
              <option value="auto">Auto</option>
              <option value="fixed">Fixed offset</option>
            </select>
          </Field>
          <Field label="Revenge window (minutes)" hint="A trade opened this soon after a losing close is flagged.">
            <input type="number" className={inputCls} value={s.revenge_minutes} onChange={(e) => setS({ ...s, revenge_minutes: Number(e.target.value) })} />
          </Field>
          <Field label="Max trades per day" hint="Trades beyond this count as overtrading.">
            <input type="number" className={inputCls} value={s.max_trades_per_day} onChange={(e) => setS({ ...s, max_trades_per_day: Number(e.target.value) })} />
          </Field>
          <Field label="Early-exit threshold (%)" hint="Winners that keep less than this share of their best open profit.">
            <input type="number" className={inputCls} value={Math.round(s.early_exit_capture * 100)} onChange={(e) => setS({ ...s, early_exit_capture: Number(e.target.value) / 100 })} />
          </Field>
        </div>
        <Field label="Sessions">
          <SessionsEditor value={s.sessions} onChange={(sessions) => setS({ ...s, sessions })} />
        </Field>
        <Field label="My trading rules" hint="Claude checks your behaviour against these in every review.">
          <textarea className={inputCls} rows={6} value={s.trading_rules} onChange={(e) => setS({ ...s, trading_rules: e.target.value })} placeholder={'1. Risk max 1% per trade\n2. Always use a stop-loss…'} />
        </Field>
        {save.error && <ErrorBox error={save.error} />}
        {save.isSuccess && <p className="text-xs text-pos">Saved</p>}
      </div>
    </Card>
  )
}

function TagsCard({ tags }: { tags: Tags }) {
  const qc = useQueryClient()
  const save = useMutation({
    mutationFn: ({ category, names }: { category: string; names: string[] }) => api.putTags(category, names),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tags'] }),
  })
  return (
    <Card title="Tag lists">
      <div className="space-y-4">
        {(['setup', 'emotion', 'mistake'] as const).map((cat) => (
          <TagList key={cat} label={`${cat[0].toUpperCase()}${cat.slice(1)}s`} names={tags[cat]} onSave={(names) => save.mutate({ category: cat, names })} />
        ))}
        <p className="text-xs text-muted">New tags you type on a trade (or Claude adds) are added here automatically. Removing a tag doesn't change past trades.</p>
      </div>
    </Card>
  )
}

function TagList({ label, names, onSave }: { label: string; names: string[]; onSave: (n: string[]) => void }) {
  const [draft, setDraft] = useState('')
  return (
    <Field label={label}>
      <div className="flex flex-wrap gap-1.5">
        {names.map((n) => (
          <span key={n} className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-ink-2">
            {n}
            <button type="button" aria-label={`Remove ${n}`} onClick={() => onSave(names.filter((x) => x !== n))} className="text-muted hover:text-neg">
              <X size={11} />
            </button>
          </span>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && draft.trim()) {
              e.preventDefault()
              onSave([...names, draft.trim()])
              setDraft('')
            }
          }}
          placeholder="Add + Enter"
          aria-label={`Add ${label}`}
          className="w-28 rounded-md border border-dashed border-border bg-transparent px-2 py-1 text-xs text-ink placeholder:text-muted focus:outline-none"
        />
      </div>
    </Field>
  )
}

export function SettingsPage() {
  const { data: settings, error } = useQuery({ queryKey: ['settings'], queryFn: api.settings })
  const { data: tags } = useQuery({ queryKey: ['tags'], queryFn: api.tags })
  return (
    <>
      <PageHeader title="Settings" />
      {error && <ErrorBox error={error} />}
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="space-y-4">
          <Mt5Card />
          <ClaudeCard />
        </div>
        <div className="space-y-4">
          {settings ? <PreferencesCard settings={settings} /> : <Spinner />}
          {tags && <TagsCard tags={tags} />}
        </div>
      </div>
    </>
  )
}
