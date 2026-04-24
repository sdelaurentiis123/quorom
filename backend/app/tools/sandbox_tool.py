"""Docker-isolated Python sandbox.

We pipe the snippet via stdin rather than bind-mounting a tempdir. This
avoids virtiofs/mount issues on macOS Docker backends (Docker Desktop OK,
colima only mounts $HOME by default) and means there's no path-quoting
dance to worry about.

  cat snippet.py | docker run --rm -i --network=none --memory=512m --cpus=1
                              quorum-sandbox:latest python -

If config.SANDBOX_DEGRADED is True (startup probe failed), we return a
structured error so the LLM can reason about the failure rather than crash.
"""
from __future__ import annotations

import asyncio
import logging

from .. import config

log = logging.getLogger("quorum.tools.sandbox")


async def sandbox_run(code: str, timeout_s: int = 20) -> dict:
    if config.SANDBOX_DEGRADED:
        return {
            "ok": False,
            "reason": "sandbox_offline",
            "hint": "Docker daemon or quorum-sandbox:latest image is not available. "
                    "Proceed without running this snippet; rely on reasoning instead.",
        }

    timeout_s = max(1, min(int(timeout_s), config.SANDBOX_CALL_TIMEOUT_S))
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "run", "--rm", "-i",
            "--network=none",
            "--memory=512m", "--cpus=1",
            config.SANDBOX_IMAGE, "python", "-",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        config.SANDBOX_DEGRADED = True
        return {"ok": False, "reason": "sandbox_offline", "hint": "docker CLI not found"}

    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(input=code.encode("utf-8")),
            timeout=timeout_s,
        )
    except asyncio.TimeoutError:
        proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            pass
        return {"ok": False, "reason": "timeout", "stdout": "", "stderr": f"killed after {timeout_s}s"}

    rc = proc.returncode
    return {
        "ok": rc == 0,
        "returncode": rc,
        "stdout": stdout_b.decode("utf-8", errors="replace")[-4000:],
        "stderr": stderr_b.decode("utf-8", errors="replace")[-2000:],
    }
