import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import { BarChart3, CalendarDays, LayoutDashboard, List, RefreshCw, Settings, Sparkles } from 'lucide-react'
import type { ReactNode } from 'react'
import { isRouteErrorResponse, Link, NavLink, Outlet, useRouteError } from 'react-router-dom'
import { api } from '../lib/api'
import { ago, currency } from '../lib/format'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/calendar', label: 'Calendar', icon: CalendarDays },
  { to: '/trades', label: 'Trades', icon: List },
  { to: '/instruments', label: 'Instruments', icon: BarChart3 },
  { to: '/coach', label: 'AI Coach', icon: Sparkles },
  { to: '/settings', label: 'Settings', icon: Settings },
]

function Brand() {
  return (
    <Link to="/" className="flex items-center gap-2.5 px-4 py-5 md:px-5">
      <span className="grid size-8 place-items-center rounded-xl bg-gradient-to-br from-accent to-accent-strong shadow-lg shadow-accent/25">
        <svg viewBox="0 0 32 32" className="size-5" aria-hidden>
          <path d="M6 22l6-7 5 4 9-11" fill="none" stroke="white" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      <span className="leading-tight">
        <span className="block text-[15px] font-semibold tracking-tight">Trading Journal</span>
        <span className="block text-[11px] text-muted">MT5 · AI coach</span>
      </span>
    </Link>
  )
}

function AccountStatus() {
  const qc = useQueryClient()
  const { data } = useQuery({ queryKey: ['status'], queryFn: api.status, refetchInterval: 15_000 })
  const sync = useMutation({ mutationFn: () => api.sync(), onSuccess: () => qc.invalidateQueries() })
  const mt5 = data?.accounts.filter((a) => a.source === 'mt5') ?? []
  const seen = mt5.map((a) => a.ea_seen_at).filter(Boolean).sort().at(-1) ?? null
  const live = seen !== null && Date.now() - new Date(seen).getTime() < 3 * 60_000
  const main = mt5[0]
  const label = !data ? 'Checking…' : !data.mt5_folder_exists ? 'MT5 not connected' : live ? 'MT5 live' : mt5.length ? 'EA idle' : 'Waiting for EA'
  return (
    <div className="rounded-2xl border border-border bg-gradient-to-b from-surface-2/80 to-surface p-3.5 text-xs shadow-[inset_0_1px_0_0_rgb(255_255_255/0.04)]">
      {main && main.balance !== null && (
        <div className="mb-3">
          <div className="text-[11px] text-muted">Balance</div>
          <div className="num text-lg font-semibold tracking-tight">{currency(main.balance, main.currency)}</div>
        </div>
      )}
      <div className="flex items-center gap-2">
        <span className="relative flex size-2">
          {live && <span className="absolute inline-flex size-full animate-ping rounded-full bg-pos opacity-60" />}
          <span className={clsx('relative inline-flex size-2 rounded-full', live ? 'bg-pos' : data?.mt5_folder_exists ? 'bg-warn' : 'bg-muted')} />
        </span>
        <span className="font-medium text-ink">{label}</span>
        {data?.demo && <span className="ml-auto rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-semibold text-accent">DEMO</span>}
      </div>
      <div className="mt-1 text-muted">EA seen {ago(seen)}</div>
      <button
        onClick={() => sync.mutate()}
        disabled={sync.isPending}
        className="mt-2.5 inline-flex items-center gap-1.5 font-medium text-accent hover:underline disabled:opacity-50"
      >
        <RefreshCw size={12} className={clsx(sync.isPending && 'animate-spin')} /> Sync now
      </button>
    </div>
  )
}

export function RouteError() {
  const error = useRouteError()
  const message = isRouteErrorResponse(error) ? `${error.status} ${error.statusText}` : error instanceof Error ? error.message : String(error)
  return (
    <div className="mx-auto max-w-lg p-10 text-center">
      <h1 className="text-lg font-semibold">Something went wrong on this page</h1>
      <p className="mt-2 text-sm text-muted">{message}</p>
      <Link to="/" className="mt-4 inline-block text-sm text-accent hover:underline">
        Back to the dashboard
      </Link>
    </div>
  )
}

export function Layout({ children }: { children?: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-border bg-page/60 backdrop-blur-xl md:sticky md:top-0 md:flex md:h-screen md:w-60 md:shrink-0 md:flex-col md:border-r md:border-b-0">
        <Brand />
        <nav className="flex gap-1 overflow-x-auto px-3 pb-3 md:flex-col md:pb-0">
          <div className="hidden px-3 pb-1.5 text-[11px] font-semibold tracking-wider text-muted/80 uppercase md:block">Menu</div>
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  'group relative flex shrink-0 items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors',
                  isActive ? 'bg-surface-3/80 text-ink shadow-[inset_0_1px_0_0_rgb(255_255_255/0.05)]' : 'text-ink-2 hover:bg-surface-2/70 hover:text-ink',
                )
              }
            >
              {({ isActive }) => (
                <>
                  {isActive && <span className="absolute top-1/2 left-0 hidden h-5 w-1 -translate-y-1/2 rounded-r-full bg-accent md:block" aria-hidden />}
                  <Icon size={17} aria-hidden className={clsx(isActive ? 'text-accent' : 'text-muted group-hover:text-ink-2')} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto hidden p-3 md:block">
          <AccountStatus />
        </div>
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 md:px-8 md:py-8">
        <div className="mx-auto max-w-7xl">
          {children ?? <Outlet />}
        </div>
      </main>
    </div>
  )
}
