"""FastAPI entrypoint. Minimal: CORS + routes + startup Docker probe."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .routes import chat as chat_routes
from .routes import paper as paper_routes
from .routes import sessions as sessions_routes
from .routes import stream as stream_routes
from .sessions import store

log = logging.getLogger("quorum")


async def _probe_sandbox() -> bool:
    """Run a one-shot Docker smoke test. Returns True if sandbox is usable."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "run", "--rm", "-i", "--network=none",
            config.SANDBOX_IMAGE, "python", "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(b"print('ok')"), timeout=10)
        return proc.returncode == 0 and b"ok" in stdout
    except (FileNotFoundError, asyncio.TimeoutError, OSError):
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    ok = await _probe_sandbox()
    if not ok:
        config.SANDBOX_DEGRADED = True
        log.warning(
            "Docker sandbox probe failed. Code-running tools will degrade to "
            "structured error until Docker is available. Run `make sandbox-image` first."
        )
    else:
        log.info("Docker sandbox probe OK.")

    watcher = asyncio.create_task(store.run_cancel_watcher())
    try:
        yield
    finally:
        watcher.cancel()


app = FastAPI(lifespan=lifespan, title="Quorum", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

app.include_router(sessions_routes.router)
app.include_router(stream_routes.router)
app.include_router(paper_routes.router)
app.include_router(chat_routes.router)


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "sandbox_degraded": config.SANDBOX_DEGRADED,
        "has_anthropic_key": bool(config.ANTHROPIC_API_KEY),
    }
