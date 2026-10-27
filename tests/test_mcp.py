import json

import pytest

from mcp import Client
from tests.helpers import deal, server_seconds, write_export
from tj.mcp_server.server import mcp

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _data(result):
    assert not result.is_error, result.content
    if result.structured_content is not None:
        sc = result.structured_content
        return sc.get("result", sc) if isinstance(sc, dict) and set(sc) == {"result"} else sc
    return json.loads(result.content[0].text)


async def test_tools_end_to_end(journal):
    t = server_seconds(2026, 10, 20, 9)
    write_export(journal, [
        deal(1, 1, t, "buy", "in", 1, 1.1000, sl=1.0950),
        deal(2, 1, t + 3600, "sell", "out", 1, 1.1050, profit=500, reason="DEAL_REASON_TP"),
    ])
    async with Client(mcp) as c:
        tools = {tool.name for tool in (await c.list_tools()).tools}
        assert {"log_trade", "annotate_trade", "get_coaching_context", "save_ai_report"} <= tools

        found = _data(await c.call_tool("find_trades", {"symbol": "EURUSD"}))
        assert found["total"] == 1
        trade_id = found["trades"][0]["id"]

        ann = _data(await c.call_tool("annotate_trade", {"trade": "last", "setup": "Breakout", "emotions": ["Calm"], "notes": "Waited for retest"}))
        assert ann["trade"]["setup"] == "Breakout" and ann["trade"]["emotions"] == ["Calm"]
        ann = _data(await c.call_tool("annotate_trade", {"trade": str(trade_id), "emotions": ["Confident"], "notes": "TP hit"}))
        assert ann["trade"]["emotions"] == ["Calm", "Confident"]

        logged = _data(await c.call_tool("log_trade", {
            "symbol": "XAUUSD", "direction": "sell", "entry_price": 2650, "exit_price": 2640, "pnl": 100,
            "open_time": "2026-10-21T10:00", "close_time": "2026-10-21T11:00", "stop_loss": 2655,
        }))
        assert logged["trade"]["source"] == "manual" and logged["trade"]["r_multiple"] == 2.0

        dup = _data(await c.call_tool("log_trade", {
            "symbol": "EURUSD", "direction": "buy", "entry_price": 1.1, "exit_price": 1.105, "pnl": 500,
            "open_time": "2026-10-20T11:05",
        }))
        assert any("looks like the same trade" in w for w in dup["warnings"])

        perf = _data(await c.call_tool("get_performance", {"period": "all", "group_by": ["instrument", "session"]}))
        assert perf["summary"]["trades"] == 3 and len(perf["by_instrument"]) == 2

        ctx = _data(await c.call_tool("get_coaching_context", {"period": "all"}))
        assert ctx["summary"]["trades"] == 3 and ctx["journal_notes"]

        saved = _data(await c.call_tool("save_ai_report", {"report": {
            "kind": "weekly", "title": "Week 43", "summary": "Solid week.",
            "action_plan": ["Keep stops"], "instruments": [{"symbol": "eurusd.m", "verdict": "edge", "headline": "Good"}],
        }}))
        assert saved["id"] and saved["view"].endswith(f"/coach/{saved['id']}")

        detail = _data(await c.call_tool("get_trade", {"trade_id": trade_id}))
        assert detail["journal"]["notes"] == "Waited for retest\n\nTP hit" and len(detail["deals"]) == 2

        assert _data(await c.call_tool("delete_trade", {"trade_id": trade_id}))["error"]
        assert _data(await c.call_tool("delete_trade", {"trade_id": dup["trade"]["id"]}))["deleted"]

        prompts = {p.name for p in (await c.list_prompts()).prompts}
        assert {"weekly_review", "instrument_review", "log_trades"} <= prompts
        prompt = await c.get_prompt("instrument_review", {"symbol": "XAUUSD"})
        assert "XAUUSD" in prompt.messages[0].content.text
