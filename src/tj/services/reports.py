"""AI coaching reports written by Claude through the MCP server."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from tj.ingest.instruments import canonical_symbol
from tj.models import AIReport

Verdict = Literal["edge", "leaking", "breakeven", "unproven"]


class InstrumentSection(BaseModel):
    symbol: str = Field(description="Instrument, e.g. EURUSD or XAUUSD")
    verdict: Verdict = Field(description="edge = profitable with consistency; leaking = losing money; breakeven; unproven = too few trades")
    headline: str = Field(description="One sentence: the single most important thing about this instrument")
    doing_well: list[str] = Field(default_factory=list, description="What is working, each backed by a number")
    going_wrong: list[str] = Field(default_factory=list, description="What is costing money, each backed by a number")
    improvements: list[str] = Field(default_factory=list, description="Specific changes to make on this instrument")
    rules: list[str] = Field(default_factory=list, description="Concrete if/then rules to adopt, e.g. 'No XAUUSD trades in Asia session'")


class AIReportIn(BaseModel):
    kind: Literal["weekly", "monthly", "instrument", "custom"]
    title: str
    summary: str = Field(description="3-5 sentence overview of the period in plain language")
    period_start: date | None = None
    period_end: date | None = None
    symbol: str | None = Field(None, description="Set for instrument reviews")
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    psychology: list[str] = Field(default_factory=list, description="Behavioural/emotional patterns seen in flags and journal notes")
    action_plan: list[str] = Field(default_factory=list, description="3-5 concrete actions for the next period")
    instruments: list[InstrumentSection] = Field(default_factory=list)
    progress_vs_previous: str | None = Field(None, description="How the trader did against the previous report's action plan")
    discipline_score: int | None = Field(None, ge=1, le=10, description="1-10: how well the trader followed sound process")


def save_report(session: Session, report: AIReportIn) -> AIReport:
    content = report.model_dump(mode="json")
    for section in content["instruments"]:
        section["symbol"] = canonical_symbol(section["symbol"])
    row = AIReport(
        kind=report.kind,
        symbol=canonical_symbol(report.symbol) if report.symbol else None,
        period_start=report.period_start,
        period_end=report.period_end,
        title=report.title,
        summary=report.summary,
        content=content,
    )
    session.add(row)
    session.flush()
    return row


def report_dict(r: AIReport, full: bool = True) -> dict[str, Any]:
    d = {
        "id": r.id,
        "created_at": r.created_at.isoformat(),
        "kind": r.kind,
        "symbol": r.symbol,
        "period_start": r.period_start.isoformat() if r.period_start else None,
        "period_end": r.period_end.isoformat() if r.period_end else None,
        "title": r.title,
        "summary": r.summary,
        "source": r.source,
    }
    if full:
        d["content"] = r.content
    else:
        d["action_plan"] = r.content.get("action_plan", [])
        d["instruments"] = [s["symbol"] for s in r.content.get("instruments", [])]
    return d


def list_reports(session: Session, limit: int = 50, symbol: str | None = None) -> list[AIReport]:
    stmt = select(AIReport).order_by(AIReport.created_at.desc()).limit(limit)
    rows = list(session.scalars(stmt))
    if symbol:
        sym = canonical_symbol(symbol)
        rows = [r for r in rows if r.symbol == sym or any(s["symbol"] == sym for s in r.content.get("instruments", []))]
    return rows


def latest_instrument_section(session: Session, symbol: str) -> dict[str, Any] | None:
    sym = canonical_symbol(symbol)
    for r in list_reports(session, limit=100):
        for s in r.content.get("instruments", []):
            if s["symbol"] == sym:
                return {**s, "report_id": r.id, "report_title": r.title, "created_at": r.created_at.isoformat()}
    return None
