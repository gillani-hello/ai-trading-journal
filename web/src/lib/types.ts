export type Direction = 'long' | 'short'
export type Verdict = 'edge' | 'leaking' | 'breakeven' | 'unproven'

export interface Journal {
  setup: string | null
  emotions: string[]
  mistakes: string[]
  notes: string | null
  rating: number | null
  followed_plan: boolean | null
  ai_feedback: string | null
  ai_feedback_at: string | null
}

export interface Trade {
  id: number
  account_id: number
  source: 'mt5' | 'manual'
  symbol: string
  instrument: string
  direction: Direction
  status: 'open' | 'closed'
  volume: number
  open_time: string
  close_time: string | null
  entry_price: number
  exit_price: number | null
  initial_sl: number | null
  initial_tp: number | null
  final_sl: number | null
  final_tp: number | null
  risk_sl: number | null
  sl_source: 'entry' | 'added' | 'close' | null
  sl_delay_seconds: number | null
  close_reason: string | null
  commission: number
  swap: number
  gross_pnl: number
  net_pnl: number
  floating_pnl: number | null
  r_multiple: number | null
  points: number | null
  mfe_points: number | null
  mae_points: number | null
  holding_seconds: number | null
  session: string | null
  journal: Journal
  screenshot_count: number
}

export interface Deal {
  ticket: number
  time: string
  type: string
  entry: string
  volume: number
  price: number
  sl: number | null
  tp: number | null
  profit: number
  commission: number
  swap: number
  reason: string | null
}

export interface Screenshot {
  id: number
  url: string
  caption: string | null
  created_at: string
}

export interface TradeDetail extends Trade {
  screenshots: Screenshot[]
  account: { id: number; name: string; currency: string }
  deals: Deal[]
  flags: { code: string; title: string; severity: Severity }[]
}

export interface Summary {
  trades: number
  wins: number
  losses: number
  breakeven: number
  win_rate: number | null
  net_pnl: number
  gross_profit: number
  gross_loss: number
  profit_factor: number | null
  expectancy: number | null
  avg_win: number | null
  avg_loss: number | null
  payoff_ratio: number | null
  largest_win: number | null
  largest_loss: number | null
  avg_r: number | null
  total_r: number | null
  trades_with_r: number
  avg_hold_win_min: number | null
  avg_hold_loss_min: number | null
  max_consecutive_wins: number
  max_consecutive_losses: number
  max_drawdown: number
  long_trades: number
  short_trades: number
}

export interface Group {
  key: string
  trades: number
  win_rate: number | null
  net_pnl: number
  profit_factor: number | null
  expectancy: number | null
  avg_r: number | null
  avg_win: number | null
  avg_loss: number | null
}

export interface Insight {
  scope: string
  kind: 'positive' | 'negative' | 'neutral'
  text: string
  impact: number
}

export type Severity = 'high' | 'medium' | 'low'

export interface Flag {
  code: string
  title: string
  severity: Severity
  description: string
  trade_ids: number[]
  cost: number
  count: number
  extra: Record<string, unknown>
}

export interface EquityPoint {
  time: string
  trade_id: number
  pnl: number
  equity: number
}

export interface DailyPoint {
  date: string
  net_pnl: number
  trades: number
  wins: number
  losses: number
}

export interface ReportBrief {
  id: number
  title: string
  created_at: string
  summary: string
  action_plan: string[]
}

export interface AccountMoney {
  balance: number
  equity: number
  floating: number
  deposits: number
  withdrawals: number
  net_deposits: number
  trading_pnl: number
  return_pct: number | null
  reconciled: boolean
  as_of: string | null
}

export interface AccountOverview {
  accounts: (AccountMoney & { id: number; name: string; broker: string | null; login: string | null; currency: string; trade_mode: string | null })[]
  total: (AccountMoney & { currency: string; accounts: number }) | null
}

export interface BalancePoint {
  time: string
  balance: number
  change: number
  kind: 'open' | 'trade' | 'cash'
}

export interface Dashboard {
  period: { from: string | null; to: string | null }
  account: AccountOverview
  balance: BalancePoint[]
  previous: (Summary & { from: string; to: string }) | null
  today: { net_pnl: number; trades: number; floating: number }
  summary: Summary
  equity: EquityPoint[]
  daily: DailyPoint[]
  by_instrument: Group[]
  by_session: Group[]
  insights: Insight[]
  flags: Flag[]
  open_trades: number
  latest_report: ReportBrief | null
}

export interface CalendarDay {
  date: string
  in_month: boolean
  net_pnl: number
  trades: number
  wins: number
  losses: number
  win_rate: number | null
  has_note: boolean
  mood: string | null
}

export interface CalendarMonth {
  year: number
  month: number
  timezone: string
  summary: Pick<Group, 'trades' | 'win_rate' | 'net_pnl' | 'profit_factor' | 'expectancy' | 'avg_r'>
  trading_days: number
  green_days: number
  red_days: number
  best_day: CalendarDay | null
  worst_day: CalendarDay | null
  max_abs_day: number
  weeks: { week_start: string; days: CalendarDay[]; net_pnl: number; trades: number; trading_days: number }[]
}

export interface DayNote {
  date: string
  pre_session_plan: string | null
  post_session_review: string | null
  mood: string | null
  rules_followed: boolean | null
}

export interface DayDetail {
  date: string
  summary: Summary
  trades: Trade[]
  note: DayNote
}

export interface InstrumentSection {
  symbol: string
  verdict: Verdict
  headline: string
  doing_well: string[]
  going_wrong: string[]
  improvements: string[]
  rules: string[]
}

export interface InstrumentCard {
  instrument: string
  verdict: Verdict
  stats: Summary
  sessions: Group[]
  directions: Group[]
  insights: Insight[]
  flags: Flag[]
}

export interface InstrumentDetail {
  instrument: string
  verdict: Verdict
  stats: Summary
  equity: EquityPoint[]
  breakdowns: Record<string, Group[]>
  insights: Insight[]
  flags: Flag[]
  ai: (InstrumentSection & { report_id: number; report_title: string; created_at: string }) | null
}

export interface ReportListItem {
  id: number
  created_at: string
  kind: string
  symbol: string | null
  period_start: string | null
  period_end: string | null
  title: string
  summary: string
  source: string
  action_plan: string[]
  instruments: string[]
}

export interface ReportContent {
  kind: string
  title: string
  summary: string
  strengths: string[]
  weaknesses: string[]
  psychology: string[]
  action_plan: string[]
  instruments: InstrumentSection[]
  progress_vs_previous: string | null
  discipline_score: number | null
}

export interface Report extends Omit<ReportListItem, 'action_plan' | 'instruments'> {
  content: ReportContent
}

export interface Account {
  id: number
  name: string
  source: string
  login: string | null
  server: string | null
  currency: string
  balance: number | null
  equity: number | null
  margin_mode: string | null
  trade_mode: string | null
  ea_seen_at: string | null
  last_sync_at: string | null
}

export interface SyncResult {
  status: 'ok' | 'no_folder' | 'error'
  folder: string | null
  message: string | null
  finished_at: string
  accounts: { login: string; name: string; new_deals: number; trades_rebuilt: number; ea_seen_at: string | null }[]
}

export interface Status {
  mt5_folder: string | null
  mt5_folder_exists: boolean
  accounts: Account[]
  last_sync: SyncResult | null
  demo: boolean
}

export interface SessionDef {
  name: string
  start: number
  end: number
}

export interface Settings {
  display_timezone: string
  sessions: SessionDef[]
  revenge_minutes: number
  max_trades_per_day: number
  early_exit_capture: number
  trading_rules: string
  broker_time_mode: 'auto' | 'fixed'
}

export type Tags = Record<'setup' | 'emotion' | 'mistake', string[]>

export interface McpConfig {
  claude_code: string
  claude_desktop: unknown
  claude_desktop_config_path: string
  prompts: string[]
}
