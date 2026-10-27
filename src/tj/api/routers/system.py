import shlex
import shutil
from pathlib import Path
from typing import Any
from zoneinfo import available_timezones

from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from tj.api.deps import DB
from tj.config import PROJECT_ROOT, claude_desktop_config_path, discover_mt5_dir, get_settings
from tj.ingest import watcher
from tj.models import Account
from tj.services.settings import get_all_settings, update_settings

router = APIRouter(prefix="/api", tags=["system"])


def mcp_command() -> list[str]:
    uv = shutil.which("uv") or "uv"
    return [uv, "--directory", str(PROJECT_ROOT), "run", "tj", "mcp"]


@router.get("/status")
def status(session: DB) -> dict[str, Any]:
    folder = discover_mt5_dir()
    accounts = [
        {
            "id": a.id,
            "name": a.name,
            "source": a.source,
            "login": a.login,
            "server": a.server,
            "currency": a.currency,
            "balance": a.balance,
            "equity": a.equity,
            "margin_mode": a.margin_mode,
            "trade_mode": a.trade_mode,
            "ea_seen_at": a.ea_seen_at.isoformat() if a.ea_seen_at else None,
            "last_sync_at": a.last_sync_at.isoformat() if a.last_sync_at else None,
        }
        for a in session.scalars(select(Account).order_by(Account.source, Account.id))
    ]
    last = watcher.last_result
    return {
        "mt5_folder": str(folder) if folder else None,
        "mt5_folder_exists": bool(folder and folder.is_dir()),
        "accounts": accounts,
        "last_sync": last.as_dict() if last else None,
        "demo": get_settings().data_dir.name == "demo-data",
    }


@router.post("/sync")
def sync(force: bool = False) -> dict[str, Any]:
    return watcher.run_sync(force=force).as_dict()


@router.get("/settings")
def read_settings(session: DB) -> dict[str, Any]:
    return get_all_settings(session)


@router.patch("/settings")
def patch_settings(session: DB, changes: dict[str, Any]) -> dict[str, Any]:
    tz = changes.get("display_timezone")
    if tz is not None and tz not in available_timezones():
        raise HTTPException(422, f"Unknown timezone {tz}")
    try:
        return update_settings(session, changes)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/timezones")
def timezones() -> list[str]:
    return sorted(available_timezones())


@router.get("/mcp-config")
def mcp_config() -> dict[str, Any]:
    cmd = mcp_command()
    return {
        "claude_code": "claude mcp add --scope user trading-journal -- " + shlex.join(cmd),
        "claude_desktop": {"mcpServers": {"trading-journal": {"command": cmd[0], "args": cmd[1:]}}},
        "claude_desktop_config_path": str(claude_desktop_config_path()).replace(str(Path.home()), "~"),
        "prompts": ["weekly_review", "monthly_review", "instrument_review", "trade_review", "log_trades"],
    }
