import base64
from datetime import date

import pytest
from fastapi.testclient import TestClient

from tj.api.main import create_app
from tj.db import session_scope
from tj.demo import annotate, generate
from tj.ingest.mt5_files import sync_mt5

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


@pytest.fixture
def client(journal):
    generate(journal, days=45)
    with session_scope() as s:
        sync_mt5(s)
        annotate(s)
    with TestClient(create_app(watch=False)) as c:
        yield c


def test_dashboard_and_lists(client):
    dash = client.get("/api/dashboard", params={"period": "all"}).json()
    assert dash["summary"]["trades"] > 0 and dash["equity"] and dash["by_instrument"]

    page = client.get("/api/trades", params={"limit": 5, "instrument": "XAUUSD", "status": "all"}).json()
    assert page["total"] > 5 and len(page["items"]) == 5
    assert all(t["instrument"] == "XAUUSD" for t in page["items"])

    losses = client.get("/api/trades", params={"outcome": "loss", "mistake": "Revenge trade"}).json()
    assert losses["total"] > 0 and all("Revenge trade" in t["journal"]["mistakes"] for t in losses["items"])

    assert client.get("/api/stats/breakdown", params={"group_by": "weekday"}).status_code == 200
    assert client.get("/api/stats/breakdown", params={"group_by": "nope"}).status_code == 422


def test_dashboard_account_balance_and_custom_range(client):
    dash = client.get("/api/dashboard", params={"period": "all"}).json()
    total = dash["account"]["total"]
    assert total["deposits"] == 10_000 and total["reconciled"]
    assert total["balance"] == pytest.approx(10_000 + total["trading_pnl"])
    assert dash["balance"][-1]["balance"] == pytest.approx(total["balance"])  # curve ends at the MT5 balance
    assert dash["previous"] is None
    assert dash["balance"][0]["kind"] == "cash" and dash["balance"][0]["balance"] == 10_000  # starts at the deposit, not 0

    today = date.today()
    start = today.replace(day=1) if today.day > 7 else today
    ranged = client.get("/api/dashboard", params={"from": start.isoformat(), "to": today.isoformat()}).json()
    assert ranged["period"] == {"from": start.isoformat(), "to": today.isoformat()}
    assert ranged["previous"]["to"] < start.isoformat()
    assert ranged["summary"]["trades"] <= dash["summary"]["trades"]
    assert ranged["balance"][0]["kind"] == "open"

    bad = client.get("/api/dashboard", params={"from": today.isoformat(), "to": "2020-01-01"})
    assert bad.status_code == 422


def test_trade_detail_journal_and_screenshots(client):
    trade = client.get("/api/trades", params={"limit": 1}).json()["items"][0]
    detail = client.get(f"/api/trades/{trade['id']}").json()
    assert detail["deals"] and "flags" in detail

    patched = client.patch(f"/api/trades/{trade['id']}/journal", json={"setup": "Pullback", "rating": 4}).json()
    assert patched["journal"]["setup"] == "Pullback" and patched["journal"]["rating"] == 4
    assert set(patched) == set(detail)  # same shape as GET so the UI can reuse it
    assert client.patch(f"/api/trades/{trade['id']}/journal", json={"rating": 9}).status_code == 422

    up = client.post(f"/api/trades/{trade['id']}/screenshots", files={"file": ("chart.png", PNG, "image/png")}, data={"caption": "entry"})
    assert up.status_code == 200
    assert client.get(up.json()["url"]).content == PNG
    assert client.post(f"/api/trades/{trade['id']}/screenshots", files={"file": ("x.txt", b"hi", "text/plain")}).status_code == 415
    assert client.delete(f"/api/screenshots/{up.json()['id']}").json()["deleted"]
    assert client.delete(f"/api/trades/{trade['id']}").status_code == 400


def test_manual_trade_round_trip(client):
    created = client.post("/api/trades", json={"symbol": "NAS100", "direction": "long", "entry_price": 20000,
                                               "exit_price": 20100, "pnl": 100, "setup": "Breakout"}).json()
    tid = created["trade"]["id"]
    assert created["trade"]["journal"]["setup"] == "Breakout"
    assert client.delete(f"/api/trades/{tid}").json()["deleted"] == tid


def test_calendar_day_notes_instruments_reports(client):
    today = date.today()
    cal = client.get("/api/calendar", params={"month": f"{today.year}-{today.month:02d}"}).json()
    assert all(len(w["days"]) == 7 for w in cal["weeks"])
    day = next(d for w in cal["weeks"] for d in w["days"] if d["trades"])
    detail = client.get(f"/api/day/{day['date']}").json()
    assert detail["trades"]

    note = client.put(f"/api/day-notes/{day['date']}", json={"post_session_review": "Good", "mood": "calm"}).json()
    assert note["mood"] == "calm"

    insts = client.get("/api/instruments", params={"period": "all"}).json()
    assert {i["instrument"] for i in insts} >= {"EURUSD", "XAUUSD"}
    gold = client.get("/api/instruments/XAUUSD").json()
    assert gold["breakdowns"]["session"] and gold["ai"]["verdict"] == "leaking"

    reports = client.get("/api/ai-reports").json()
    assert reports and client.get(f"/api/ai-reports/{reports[0]['id']}").json()["content"]["action_plan"]


def test_settings_status_and_config(client):
    assert client.patch("/api/settings", json={"max_trades_per_day": 4}).json()["max_trades_per_day"] == 4
    assert client.patch("/api/settings", json={"display_timezone": "Mars/Base"}).status_code == 422
    assert client.patch("/api/settings", json={"bogus": 1}).status_code == 422
    status = client.get("/api/status").json()
    assert status["mt5_folder_exists"] and status["accounts"]
    assert "claude mcp add" in client.get("/api/mcp-config").json()["claude_code"]
    assert client.post("/api/sync").json()["status"] == "ok"
