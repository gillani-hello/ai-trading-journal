import clsx from 'clsx'
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Check, Copy, Info, Loader2, Minus, ThumbsUp, X, type LucideIcon } from 'lucide-react'
import { useEffect, useState, type ButtonHTMLAttributes, type ReactNode } from 'react'
import type { Insight, Severity, Verdict } from '../lib/types'
import { money, pnlClass } from '../lib/format'

export { DateRangePicker as PeriodPicker } from './DateRangePicker'

const surface =
  'rounded-2xl border border-border bg-gradient-to-b from-surface-2/70 to-surface shadow-[inset_0_1px_0_0_rgb(255_255_255/0.04),0_1px_2px_rgb(0_0_0/0.3)]'

export function Card({
  title,
  icon: Icon,
  action,
  children,
  className,
  bodyClassName,
}: {
  title?: ReactNode
  icon?: LucideIcon
  action?: ReactNode
  children: ReactNode
  className?: string
  bodyClassName?: string
}) {
  return (
    <section className={clsx(surface, 'min-w-0', className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 px-5 pt-4 pb-1">
          <h2 className="flex items-center gap-2 text-sm font-medium text-ink-2">
            {Icon && <Icon size={15} className="text-muted" aria-hidden />}
            {title}
          </h2>
          {action}
        </header>
      )}
      <div className={clsx('p-5 pt-3', bodyClassName)}>{children}</div>
    </section>
  )
}

/** Change against the previous period: arrow + amount, coloured by whether the change is good. */
export function Delta({
  value,
  previous,
  format,
  better = 'up',
}: {
  value: number | null | undefined
  previous: number | null | undefined
  format: (d: number) => string
  better?: 'up' | 'down'
}) {
  if (value === null || value === undefined || previous === null || previous === undefined) return null
  const d = value - previous
  if (Math.abs(d) < 1e-9) {
    return (
      <span className="inline-flex items-center gap-0.5 text-xs text-muted">
        <Minus size={12} aria-hidden /> no change
      </span>
    )
  }
  const good = better === 'up' ? d > 0 : d < 0
  const Icon = d > 0 ? ArrowUpRight : ArrowDownRight
  return (
    <span className={clsx('num inline-flex items-center gap-0.5 text-xs font-medium', good ? 'text-pos' : 'text-neg')}>
      <Icon size={13} aria-hidden />
      {format(d)}
    </span>
  )
}

export function Stat({
  label,
  value,
  sub,
  tone,
  icon: Icon,
  delta,
}: {
  label: string
  value: ReactNode
  sub?: ReactNode
  tone?: string
  icon?: LucideIcon
  delta?: ReactNode
}) {
  return (
    <div className={clsx(surface, 'px-4 py-3.5')}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium text-muted">{label}</span>
        {Icon && (
          <span className="grid size-6 place-items-center rounded-lg bg-surface-3/80 text-muted">
            <Icon size={13} aria-hidden />
          </span>
        )}
      </div>
      <div className={clsx('num mt-1.5 text-[1.375rem] leading-tight font-semibold tracking-tight', tone)}>{value}</div>
      {(sub || delta) && (
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-muted">
          {delta}
          {sub && <span>{sub}</span>}
        </div>
      )}
    </div>
  )
}

export function Pnl({ value, className }: { value: number | null | undefined; className?: string }) {
  return <span className={clsx('num', pnlClass(value), className)}>{money(value)}</span>
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; size?: 'sm' | 'md' }) {
  return (
    <button
      className={clsx(
        'inline-flex items-center justify-center gap-1.5 rounded-xl font-medium transition-colors focus-visible:ring-2 focus-visible:ring-accent/60 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50',
        size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-9 px-3.5 text-sm',
        variant === 'primary' && 'bg-gradient-to-b from-accent to-accent-strong text-white shadow-md shadow-accent/20 hover:brightness-110',
        variant === 'secondary' && 'border border-border bg-surface-2 text-ink hover:bg-surface-3',
        variant === 'ghost' && 'text-ink-2 hover:bg-surface-2 hover:text-ink',
        variant === 'danger' && 'border border-neg/40 text-neg hover:bg-neg/10',
        className,
      )}
      {...rest}
    />
  )
}

const controlCls =
  'rounded-xl border border-border bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-muted transition-colors focus:border-accent focus:outline-none [color-scheme:dark]'
export const inputCls = `w-full ${controlCls}`
/** Inline controls (filter bars) that size to their content. */
export const compactInputCls = controlCls

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-muted">{hint}</span>}
    </label>
  )
}

export function Badge({
  children,
  tone = 'neutral',
  className,
}: {
  children: ReactNode
  tone?: 'neutral' | 'pos' | 'neg' | 'warn' | 'accent'
  className?: string
}) {
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset',
        tone === 'neutral' && 'bg-surface-3/70 text-ink-2 ring-white/5',
        tone === 'pos' && 'bg-pos/12 text-pos ring-pos/20',
        tone === 'neg' && 'bg-neg/12 text-neg ring-neg/20',
        tone === 'warn' && 'bg-warn/12 text-warn ring-warn/20',
        tone === 'accent' && 'bg-accent/12 text-accent ring-accent/20',
        className,
      )}
    >
      {children}
    </span>
  )
}

export function SideBadge({ direction }: { direction: string }) {
  const long = direction === 'long'
  const Icon = long ? ArrowUpRight : ArrowDownRight
  return (
    <Badge tone={long ? 'accent' : 'neutral'}>
      <Icon size={12} aria-hidden />
      {long ? 'Long' : 'Short'}
    </Badge>
  )
}

const VERDICTS: Record<Verdict, { label: string; tone: 'pos' | 'neg' | 'neutral' | 'warn' }> = {
  edge: { label: 'Edge', tone: 'pos' },
  leaking: { label: 'Leaking', tone: 'neg' },
  breakeven: { label: 'Breakeven', tone: 'neutral' },
  unproven: { label: 'Too few trades', tone: 'neutral' },
}

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const v = VERDICTS[verdict]
  return <Badge tone={v.tone}>{v.label}</Badge>
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const tone = severity === 'high' ? 'neg' : severity === 'medium' ? 'warn' : 'neutral'
  return (
    <Badge tone={tone}>
      <AlertTriangle size={11} aria-hidden />
      {severity}
    </Badge>
  )
}

export function InsightRow({ insight }: { insight: Insight }) {
  const Icon = insight.kind === 'positive' ? ThumbsUp : insight.kind === 'negative' ? AlertTriangle : Info
  const tone =
    insight.kind === 'positive' ? 'bg-pos/12 text-pos' : insight.kind === 'negative' ? 'bg-neg/12 text-neg' : 'bg-surface-3 text-muted'
  return (
    <li className="flex gap-3 py-2 text-sm leading-snug">
      <span className={clsx('mt-0.5 grid size-6 shrink-0 place-items-center rounded-lg', tone)}>
        <Icon size={13} aria-label={insight.kind} />
      </span>
      <span className="text-ink-2">{insight.text}</span>
    </li>
  )
}

export function Spinner({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-6 text-sm text-muted">
      <Loader2 size={16} className="animate-spin" /> {label}
    </div>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx('animate-pulse rounded-2xl bg-surface-2/80', className)} aria-hidden />
}

export function ErrorBox({ error }: { error: unknown }) {
  return <div className="rounded-xl border border-neg/40 bg-neg/10 p-3 text-sm text-neg">{error instanceof Error ? error.message : String(error)}</div>
}

export function Empty({ title, children, icon: Icon = Info }: { title: string; children?: ReactNode; icon?: LucideIcon }) {
  return (
    <div className="rounded-2xl border border-dashed border-border bg-surface/40 p-10 text-center">
      <span className="mx-auto grid size-10 place-items-center rounded-xl bg-surface-3 text-muted">
        <Icon size={18} aria-hidden />
      </span>
      <div className="mt-3 text-sm font-medium text-ink">{title}</div>
      {children && <div className="mx-auto mt-1.5 max-w-lg text-sm text-muted">{children}</div>}
    </div>
  )
}

export function PageHeader({ title, sub, children }: { title: ReactNode; sub?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {sub && <div className="mt-1 text-sm text-muted">{sub}</div>}
      </div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  )
}

export function CopyBlock({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  useEffect(() => {
    if (!copied) return
    const t = setTimeout(() => setCopied(false), 1500)
    return () => clearTimeout(t)
  }, [copied])
  return (
    <div className="relative">
      <pre className="overflow-x-auto rounded-xl border border-border bg-page p-3 pr-10 text-xs leading-relaxed text-ink-2">{text}</pre>
      <button
        aria-label="Copy"
        onClick={() => navigator.clipboard.writeText(text).then(() => setCopied(true))}
        className="absolute top-2 right-2 rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-ink"
      >
        {copied ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </div>
  )
}

function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])
}

export function Drawer({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  useEscape(open, onClose)
  if (!open) return null
  return (
    <div className="fixed inset-0 z-40 flex justify-end">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <aside role="dialog" aria-modal className="animate-slide-in relative flex h-full w-full max-w-xl flex-col border-l border-border bg-surface shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-5 py-4">
          <div className="font-semibold">{title}</div>
          <button aria-label="Close" onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink">
            <X size={16} />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
      </aside>
    </div>
  )
}

export function Modal({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode }) {
  useEscape(open, onClose)
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto p-4 sm:p-10">
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div role="dialog" aria-modal className="animate-fade-in relative w-full max-w-2xl rounded-2xl border border-border bg-surface shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-5 py-4">
          <div className="font-semibold">{title}</div>
          <button aria-label="Close" onClick={onClose} className="rounded-lg p-1.5 text-muted hover:bg-surface-2 hover:text-ink">
            <X size={16} />
          </button>
        </header>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

export function Pnlbar({ value, max }: { value: number; max: number }) {
  const w = max > 0 ? Math.min(Math.abs(value) / max, 1) * 50 : 0
  return (
    <div className="relative h-1.5 w-full rounded-full bg-surface-3" aria-hidden>
      <div className="absolute top-0 left-1/2 h-full w-px bg-baseline" />
      <div
        className={clsx('absolute top-0 h-full rounded-full', value >= 0 ? 'bg-pos' : 'bg-neg')}
        style={value >= 0 ? { left: '50%', width: `${w}%` } : { right: '50%', width: `${w}%` }}
      />
    </div>
  )
}
