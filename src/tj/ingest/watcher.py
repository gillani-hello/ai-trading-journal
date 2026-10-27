"""Keep the journal in step with the EA's export folder."""

import asyncio
import logging
import time

from watchfiles import awatch

from tj.config import discover_mt5_dir, get_settings
from tj.db import session_scope
from tj.ingest.mt5_files import SyncResult, sync_mt5

log = logging.getLogger(__name__)

last_result: SyncResult | None = None
_last_sync_monotonic = 0.0


def run_sync(force: bool = False) -> SyncResult:
    global last_result, _last_sync_monotonic
    try:
        with session_scope() as session:
            result = sync_mt5(session, force=force)
    except Exception as exc:  # keep the server alive; surface the error in the status
        log.exception("MT5 sync failed")
        result = SyncResult(status="error", folder=str(discover_mt5_dir()), message=str(exc))
    _last_sync_monotonic = time.monotonic()
    last_result = result
    for acc in result.accounts:
        if acc.new_deals or acc.trades_rebuilt:
            log.info("MT5 %s: %d new deals, %d trades updated", acc.login, acc.new_deals, acc.trades_rebuilt)
    return result


def maybe_sync() -> SyncResult | None:
    """Sync unless one ran recently (used before answering MCP tool calls)."""
    if time.monotonic() - _last_sync_monotonic < get_settings().sync_throttle_seconds:
        return None
    return run_sync()


async def watch_forever(stop: asyncio.Event) -> None:
    """Sync on start, then whenever the EA rewrites a file (with a 60 s safety poll)."""
    while not stop.is_set():
        folder = discover_mt5_dir()
        if folder is None or not folder.is_dir():
            await asyncio.to_thread(run_sync)
            try:
                await asyncio.wait_for(stop.wait(), timeout=30)
            except TimeoutError:
                pass
            continue
        await asyncio.to_thread(run_sync)
        try:
            async for changes in awatch(
                folder, stop_event=stop, debounce=800, rust_timeout=60_000, yield_on_timeout=True
            ):
                if not changes or any(not path.endswith(".tmp") for _, path in changes):
                    await asyncio.to_thread(run_sync)
        except Exception:
            log.exception("Watching %s failed; retrying", folder)
            await asyncio.sleep(5)
