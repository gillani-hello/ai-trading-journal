from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from tests.helpers import LOGIN, balance, deal, server_seconds, write_export
from tj.db import session_scope
from tj.ingest.instruments import asset_class, canonical_symbol, server_ms_to_utc
from tj.ingest.mt5_files import sync_mt5
from tj.models import CashFlow, Deal, Trade, TradeJournal


def _sync(force=False):
    with session_scope() as s:
        return sync_mt5(s, force=force)


def _trades():
    with session_scope() as s:
        return list(s.scalars(select(Trade).order_by(Trade.position_id, Trade.leg)))


def test_simple_long_trade(journal):
    t0 = server_seconds(2026, 7, 6, 8, 0)  # 08:00 UTC, London
    t1 = server_seconds(2026, 7, 6, 10, 30)
    write_export(
        journal,
        [
            deal(1, 100, t0, "buy", "in", 1.0, 1.1000, sl=1.0950, tp=1.1100, commission=-3.0),
            deal(2, 100, t1, "sell", "out", 1.0, 1.1050, profit=500, commission=-3.0, swap=-1.0,
                 sl=1.0950, tp=1.1100, reason="DEAL_REASON_TP"),
        ],
        excursions=[(100, 1.1080, 1.0980)],
    )
    result = _sync()
    assert result.status == "ok" and result.accounts[0].new_deals == 2

    [t] = _trades()
    assert (t.direction, t.status, t.instrument, t.session) == ("long", "closed", "EURUSD", "London")
    assert t.open_time == datetime(2026, 7, 6, 8, 0, tzinfo=UTC)
    assert t.holding_seconds == 2.5 * 3600
    assert t.net_pnl == pytest.approx(493.0)
    assert t.commission == -6.0 and t.swap == -1.0
    assert t.r_multiple == pytest.approx(1.0)
    assert t.points == pytest.approx(500)
    assert t.mfe_points == pytest.approx(800) and t.mae_points == pytest.approx(200)
    assert t.close_reason == "tp"


def test_partial_closes_are_volume_weighted(journal):
    t = server_seconds(2026, 3, 2, 14)
    write_export(
        journal,
        [
            deal(1, 7, t, "sell", "in", 2.0, 2000.0, symbol="XAUUSD.m", sl=2010.0),
            deal(2, 7, t + 600, "buy", "out", 1.0, 1990.0, symbol="XAUUSD.m", profit=1000),
            deal(3, 7, t + 1200, "buy", "out", 1.0, 1980.0, symbol="XAUUSD.m", profit=2000,
                 reason="DEAL_REASON_SL"),
        ],
    )
    _sync()
    [tr] = _trades()
    assert tr.instrument == "XAUUSD" and tr.direction == "short" and tr.status == "closed"
    assert tr.volume == 2.0 and tr.exit_price == pytest.approx(1985.0)
    assert tr.r_multiple == pytest.approx(1.5)
    assert tr.close_reason == "sl"


def test_open_position_uses_floating_pnl(journal):
    t = server_seconds(2026, 3, 2, 3)
    write_export(
        journal,
        [deal(1, 9, t, "buy", "in", 2.0, 1.2000), deal(2, 9, t + 60, "sell", "out", 1.0, 1.2010, profit=100)],
        positions=[{"position_id": 9, "symbol": "EURUSD", "type": "POSITION_TYPE_BUY", "volume": 1.0,
                    "price_open": 1.2, "price_current": 1.203, "sl": 1.19, "tp": 1.21, "profit": 300, "swap": -2}],
    )
    _sync()
    [tr] = _trades()
    assert tr.status == "open" and tr.close_time is None
    assert tr.net_pnl == 100 and tr.floating_pnl == 298
    assert tr.final_sl == 1.19 and tr.session == "Asia"


def test_netting_reversal_splits_into_two_trades(journal):
    t = server_seconds(2026, 3, 2, 13)
    write_export(
        journal,
        [deal(1, 5, t, "buy", "in", 1.0, 100.0), deal(2, 5, t + 60, "sell", "inout", 3.0, 90.0, profit=-10)],
        symbols=[],
        margin_mode="netting",
    )
    _sync()
    first, second = _trades()
    assert (first.direction, first.status, first.exit_price, first.net_pnl) == ("long", "closed", 90.0, -10)
    assert first.close_reason == "reversal"
    assert (second.direction, second.status, second.volume, second.entry_price) == ("short", "open", 2.0, 90.0)


def test_resync_is_idempotent_and_keeps_journal(journal):
    t = server_seconds(2026, 3, 2, 9)
    deals = [deal(1, 1, t, "buy", "in", 1, 1.1), deal(2, 1, t + 60, "sell", "out", 1, 1.2, profit=10),
             balance(3, t - 3600, 5000)]
    write_export(journal, deals)
    _sync()
    with session_scope() as s:
        trade = s.scalars(select(Trade)).one()
        s.add(TradeJournal(trade_id=trade.id, setup="Breakout", notes="good patience"))
        trade_id = trade.id

    _sync()
    _sync(force=True)
    with session_scope() as s:
        assert s.query(Deal).count() == 3
        assert s.query(Trade).count() == 1
        assert s.query(CashFlow).one().amount == 5000
        trade = s.get(Trade, trade_id)
        assert trade.journal.setup == "Breakout" and trade.journal.notes == "good patience"


def test_new_deals_are_picked_up(journal):
    t = server_seconds(2026, 3, 2, 9)
    deals = [deal(1, 1, t, "buy", "in", 1, 1.1)]
    write_export(journal, deals)
    _sync()
    assert _trades()[0].status == "open"
    deals.append(deal(2, 1, t + 60, "sell", "out", 1, 1.2, profit=10))
    write_export(journal, deals)
    result = _sync()
    assert result.accounts[0].new_deals == 1
    assert _trades()[0].status == "closed"


def test_risk_stop_sources(journal):
    t = server_seconds(2026, 7, 6, 8)
    write_export(
        journal,
        [
            # 1: stop added 3 min after a mobile entry (seen by the EA)
            deal(1, 1, t, "buy", "in", 1, 1.1000, reason="DEAL_REASON_MOBILE"),
            deal(2, 1, t + 3600, "sell", "out", 1, 1.0980, profit=-200, sl=1.0980, reason="DEAL_REASON_SL"),
            # 2: no stop on the order or seen by the EA; stop at close was still protective
            deal(3, 2, t, "sell", "in", 1, 1.1000),
            deal(4, 2, t + 3600, "buy", "out", 1, 1.0950, profit=500, sl=1.1025),
            # 3: stop only ever at breakeven: no risk stop, no R
            deal(5, 3, t, "buy", "in", 1, 1.1000),
            deal(6, 3, t + 3600, "sell", "out", 1, 1.1030, profit=300, sl=1.1000),
            # 4: stop trailed to just below entry after price dipped past it: not the original risk
            deal(7, 4, t, "buy", "in", 1, 1.1000),
            deal(8, 4, t + 3600, "sell", "out", 1, 1.1040, profit=400, sl=1.0998),
            # 5: price never came near the closing stop, but it would imply 8R: rejected
            deal(9, 5, t, "buy", "in", 1, 1.1000),
            deal(10, 5, t + 3600, "sell", "out", 1, 1.1040, profit=400, sl=1.0995),
            # 6: stop trailed to just under entry after a big run, then hit: not a real -1R
            deal(11, 6, t, "buy", "in", 1, 1.1000),
            deal(12, 6, t + 3600, "sell", "out", 1, 1.0999, profit=-10, sl=1.0999, reason="DEAL_REASON_SL"),
        ],
        excursions=[(2, 1.1010, 1.0940), (4, 1.1045, 1.0990), (5, 1.1045, 1.0999), (6, 1.1050, 1.0999)],
    )
    (journal / f"stops_{LOGIN}.csv").write_text(f"position_id,first_sl,first_sl_time\r\n1,1.0960,{t + 180}\r\n")
    _sync()
    a, b, c, d, e, f = _trades()
    assert (a.risk_sl, a.sl_source, a.sl_delay_seconds) == (1.0960, "added", 180)
    assert a.r_multiple == pytest.approx(-0.5)  # lost 20 pips of a 40-pip stop
    assert (b.risk_sl, b.sl_source) == (1.1025, "close") and b.r_multiple == pytest.approx(2.0)
    assert (c.risk_sl, c.sl_source, c.r_multiple) == (None, None, None)
    assert (d.risk_sl, d.r_multiple) == (None, None)
    assert (e.risk_sl, e.r_multiple) == (None, None)
    assert (f.risk_sl, f.r_multiple) == (None, None)


def test_no_folder(journal, monkeypatch, tmp_path):
    with session_scope() as s:
        assert sync_mt5(s, folder=tmp_path / "missing").status == "no_folder"


@pytest.mark.parametrize(
    "raw,expected",
    [("EURUSD.m", "EURUSD"), ("EURUSDm", "EURUSD"), ("XAUUSD+", "XAUUSD"), ("#US30", "US30"),
     ("US30.cash", "US30"), ("GER40", "GER40"), ("BTCUSD", "BTCUSD")],
)
def test_canonical_symbol(raw, expected):
    assert canonical_symbol(raw) == expected


def test_asset_class():
    assert asset_class("EURUSD.m") == "forex"
    assert asset_class("XAUUSD") == "metals"
    assert asset_class("XYZ", "Indices\\XYZ") == "indices"
    assert asset_class("BTCUSD") == "crypto"


def test_ny_close_broker_time_follows_us_dst():
    summer = server_seconds(2026, 7, 1, 12, offset_hours=3) * 1000
    winter = server_seconds(2026, 1, 15, 12, offset_hours=2) * 1000
    # The EA reports today's offset (+3 in summer); January deals were at +2.
    assert server_ms_to_utc(summer, 10800).hour == 12
    assert server_ms_to_utc(winter, 10800).hour == 12
    assert server_ms_to_utc(winter, 10800, mode="fixed").hour == 11
