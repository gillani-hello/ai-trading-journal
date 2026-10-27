from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from tj.db import session_scope
from tj.ingest.mt5_files import sync_mt5
from tj.services.analytics import TradeRow, group_stats, instrument_verdict, max_drawdown, summarize
from tj.services.behavior import detect
from tj.services.settings import DEFAULTS

UTC_TZ = ZoneInfo("UTC")
T0 = datetime(2026, 3, 2, 8, 0, tzinfo=UTC)  # Monday


def row(i, net, *, minutes=0, hold=60, inst="EURUSD", vol=1.0, r=None, sl=0.95, final_sl=None, sl_source="entry",
        direction="long", points=None, mfe=None, session="London", reason="manual", source="mt5", emotions=(), delay=None):
    opened = T0 + timedelta(minutes=minutes)
    return TradeRow(
        id=i, instrument=inst, direction=direction, source=source, open_time=opened,
        close_time=opened + timedelta(minutes=hold), volume=vol, net_pnl=net, entry_price=1.0, exit_price=1.0,
        r_multiple=r, points=points, mfe_points=mfe, mae_points=None, holding_seconds=hold * 60,
        session=session, close_reason=reason, initial_sl=sl if sl_source == "entry" else None,
        final_sl=final_sl if final_sl is not None else sl, risk_sl=sl, sl_source=sl_source if sl else None,
        sl_delay_seconds=delay, emotions=list(emotions),
    )  # fmt: skip


def test_summary_numbers():
    rows = [row(1, 100, r=2), row(2, -50, minutes=100, r=-1), row(3, 200, minutes=200, r=1.5), row(4, -50, minutes=300, r=-1)]
    s = summarize(rows)
    assert s["trades"] == 4 and s["wins"] == 2 and s["losses"] == 2
    assert s["win_rate"] == 0.5
    assert s["net_pnl"] == 200
    assert s["profit_factor"] == 3.0
    assert s["expectancy"] == 50
    assert s["avg_win"] == 150 and s["avg_loss"] == -50 and s["payoff_ratio"] == 3.0
    assert s["avg_r"] == pytest.approx(0.38, abs=0.01)
    assert s["max_drawdown"] == 50


def test_max_drawdown_peak_to_trough():
    rows = [row(1, 100), row(2, -30, minutes=10), row(3, -40, minutes=20), row(4, 10, minutes=30), row(5, -60, minutes=40)]
    assert max_drawdown(rows) == 120


def test_group_by_emotion_counts_each_tag():
    rows = [row(1, -10, emotions=["FOMO", "Fear"]), row(2, 20, minutes=90, emotions=["Calm"]), row(3, -5, minutes=200)]
    groups = {g["key"]: g for g in group_stats(rows, "emotion", UTC_TZ)}
    assert groups["FOMO"]["trades"] == 1 and groups["Fear"]["net_pnl"] == -10
    assert groups["(none)"]["trades"] == 1


def test_verdicts():
    assert instrument_verdict(summarize([row(1, 10)])) == "unproven"
    assert instrument_verdict(summarize([row(i, -10, minutes=i * 90) for i in range(6)])) == "leaking"
    assert instrument_verdict(summarize([row(i, 10 if i % 3 else -5, minutes=i * 90) for i in range(9)])) == "edge"


def _codes(rows, **overrides):
    return {f.code: f for f in detect(rows, {**DEFAULTS, **overrides}, UTC_TZ)}


def test_revenge_trade_detected_with_bigger_size():
    rows = [row(1, -100, hold=30), row(2, -150, minutes=40, vol=2.0)]  # opened 10 min after the losing close
    f = _codes(rows)["revenge_trading"]
    assert f.trade_ids == [2] and f.extra["bigger_size"] == 1 and f.severity == "high"


def test_no_stop_and_widened_stop():
    rows = [row(1, -80, sl=None), row(2, -120, minutes=100, sl=0.95, final_sl=0.9),
            row(3, -50, minutes=200, sl=0.95, final_sl=0.949)]  # nudged by 2% of risk: not widened
    codes = _codes(rows)
    assert codes["no_stop_loss"].trade_ids == [1]
    assert codes["stop_widened"].trade_ids == [2]


def test_stop_added_after_entry_is_not_no_stop():
    rows = [row(1, -80, sl_source="added", delay=120), row(2, 40, minutes=100, sl_source="close"),
            row(3, 30, minutes=200), row(4, 20, minutes=300, sl=None, final_sl=1.01)]  # 4: only a trailed stop
    codes = _codes(rows)
    assert "no_stop_loss" not in codes
    late = codes["late_stop"]
    assert late.trade_ids == [1, 2, 4] and late.extra["median_delay_seconds"] == 120 and late.severity == "medium"


def test_loss_beyond_plan_and_early_exit():
    rows = [row(1, -300, r=-3.0), row(2, 50, minutes=100, points=10, mfe=100)]
    codes = _codes(rows)
    assert codes["loss_beyond_plan"].cost == pytest.approx(-200)
    assert codes["early_exits"].extra["left_on_table"] == pytest.approx(450)


def test_overtrading():
    rows = [row(i, -10, minutes=i * 70) for i in range(8)]
    f = _codes(rows, max_trades_per_day=6)["overtrading"]
    assert len(f.trade_ids) == 2


def test_demo_data_flows_through_everything(journal):
    from tj.demo import annotate, generate
    from tj.services.calendar import month_calendar
    from tj.services.coaching import coaching_context, dashboard, instrument_breakdown, instrument_detail
    from tj.services.trades import TradeFilter

    stats = generate(journal, days=60)
    assert stats["trades"] > 80
    with session_scope() as s:
        result = sync_mt5(s)
        assert result.status == "ok"
        annotate(s)
    with session_scope() as s:
        breakdown = {b["instrument"]: b for b in instrument_breakdown(s, TradeFilter())}
        assert set(breakdown) >= {"EURUSD", "XAUUSD", "US30"}
        assert breakdown["XAUUSD"]["stats"]["net_pnl"] < breakdown["EURUSD"]["stats"]["net_pnl"]
        detail = instrument_detail(s, "XAUUSD", TradeFilter())
        assert detail["insights"] and detail["flags"]
        ctx = coaching_context(s, period="month")
        assert ctx["summary"]["trades"] > 0 and ctx["behaviour_flags"]
        assert any(f["code"] == "revenge_trading" for f in ctx["behaviour_flags"])
        today = date.today()
        cal = month_calendar(s, today.year, today.month)
        assert len(cal["weeks"]) >= 4 and all(len(w["days"]) == 7 for w in cal["weeks"])
        dash = dashboard(s, TradeFilter())
        assert dash["open_trades"] == 2 and dash["latest_report"]
