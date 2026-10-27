"""FastAPI app: REST API, screenshots, the built web UI, and the MT5 folder watcher."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from tj.api.routers import stats, system, trades
from tj.config import get_settings
from tj.db import init_db
from tj.ingest.watcher import watch_forever

log = logging.getLogger(__name__)


def create_app(watch: bool = True) -> FastAPI:
    settings = get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        init_db()
        stop = asyncio.Event()
        task = asyncio.create_task(watch_forever(stop)) if watch else None
        yield
        stop.set()
        if task:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="Trading Journal", lifespan=lifespan)
    for router in (trades.router, stats.router, system.router):
        app.include_router(router)
    app.mount("/screenshots", StaticFiles(directory=settings.screenshots_dir), name="screenshots")

    dist = settings.web_dist
    if (dist / "index.html").is_file():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str) -> FileResponse:
            if path.startswith("api/"):
                raise HTTPException(404)
            candidate = (dist / path).resolve()
            if path and candidate.is_file() and dist.resolve() in candidate.parents:
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")
    else:
        log.warning("Web UI not built (%s missing). Run `npm run build` in web/.", dist / "index.html")

    return app
