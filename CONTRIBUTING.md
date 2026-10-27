# Contributing to AI Trading Journal

Thanks for helping make a better free trading journal. Bug reports, ideas and pull requests are all welcome.

## Development setup

```bash
uv sync                               # Python deps
uv run tj seed-demo                   # demo journal in demo-data/
uv run tj serve --demo --port 8765    # API + watcher
cd web && npm install && npm run dev  # UI with hot reload on :5173 (proxies /api)
uv run pytest                         # backend tests
```

## Project layout

| Path | What's there |
|---|---|
| `mt5/TradeJournalSync.mq5` | The read-only MT5 Expert Advisor that exports history |
| `src/tj/ingest/` | Reads the EA's files; builds trades from deals |
| `src/tj/services/` | Analytics, behaviour flags, insights, calendar, journal, AI reports |
| `src/tj/api/` | FastAPI REST API (also serves the built UI) |
| `src/tj/mcp_server/` | MCP tools and prompts for Claude |
| `web/` | React + Vite + Tailwind UI |
| `tests/` | pytest suite, using EA-format fixtures |

## Guidelines

- Keep the EA read-only: it must never place, modify or close trades.
- Add a test for every change to trade reconstruction or statistics. Real money decisions get made on these numbers.
- Never commit real account data: `data/` and `demo-data/` are git-ignored. Use `tj seed-demo` for screenshots.
- Schema changes need a migration: `uv run tj db-revision "what changed"`.

## Reporting bugs

Please include your OS, how MT5 is installed (Windows, the Mac app, Wine), your broker's account type (hedging or netting), and the `TradeJournalSync` lines from MT5's **Experts** tab. Redact your account number.
