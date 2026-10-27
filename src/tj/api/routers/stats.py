from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException

from tj.api.deps import DB, Filter
from tj.models import AIReport
from tj.services import coaching, reports
from tj.services.analytics import group_stats, summarize
from tj.services.behavior import detect
from tj.services.calendar import month_calendar
from tj.services.insights import overall_insights
from tj.services.settings import get_all_settings
from tj.services.trades import get_tz, load_rows

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/dashboard")
def dashboard(session: DB, f: Filter) -> dict[str, Any]:
    return coaching.dashboard(session, f)


@router.get("/stats/summary")
def stats_summary(session: DB, f: Filter) -> dict[str, Any]:
    return summarize(load_rows(session, f))


@router.get("/stats/breakdown")
def stats_breakdown(session: DB, f: Filter, group_by: str = "instrument") -> list[dict[str, Any]]:
    try:
        return group_stats(load_rows(session, f), group_by, get_tz(session))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/insights")
def insights(session: DB, f: Filter) -> list[dict[str, Any]]:
    return [i.as_dict() for i in overall_insights(load_rows(session, f), get_tz(session), limit=20)]


@router.get("/behavior")
def behavior(session: DB, f: Filter) -> list[dict[str, Any]]:
    rows = load_rows(session, f)
    return [x.as_dict() for x in detect(rows, get_all_settings(session), get_tz(session))]


@router.get("/calendar")
def calendar(session: DB, month: str | None = None, account_id: int | None = None) -> dict[str, Any]:
    today = datetime.now(get_tz(session)).date()
    try:
        year, mon = (int(x) for x in month.split("-")) if month else (today.year, today.month)
    except ValueError as exc:
        raise HTTPException(422, "month must be YYYY-MM") from exc
    return month_calendar(session, year, mon, account_id)


@router.get("/instruments")
def instruments(session: DB, f: Filter) -> list[dict[str, Any]]:
    return coaching.instrument_breakdown(session, f)


@router.get("/instruments/{symbol}")
def instrument(session: DB, f: Filter, symbol: str) -> dict[str, Any]:
    return coaching.instrument_detail(session, symbol, f)


@router.get("/ai-reports")
def list_ai_reports(session: DB, symbol: str | None = None) -> list[dict[str, Any]]:
    return [reports.report_dict(r, full=False) for r in reports.list_reports(session, symbol=symbol)]


@router.get("/ai-reports/{report_id}")
def get_ai_report(session: DB, report_id: int) -> dict[str, Any]:
    r = session.get(AIReport, report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    return reports.report_dict(r)


@router.delete("/ai-reports/{report_id}")
def delete_ai_report(session: DB, report_id: int) -> dict[str, Any]:
    r = session.get(AIReport, report_id)
    if r is None:
        raise HTTPException(404, "Report not found")
    session.delete(r)
    return {"deleted": report_id}
