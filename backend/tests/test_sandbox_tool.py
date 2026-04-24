"""Sandbox tests — gated on Docker availability."""
from __future__ import annotations

import asyncio
import shutil

import pytest

from app import config
from app.tools.sandbox_tool import sandbox_run

_has_docker = shutil.which("docker") is not None


async def _docker_works() -> bool:
    if not _has_docker:
        return False
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "run", "--rm", config.SANDBOX_IMAGE, "python", "-c", "print('ok')",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=12)
        return proc.returncode == 0 and b"ok" in stdout
    except (asyncio.TimeoutError, FileNotFoundError):
        return False


@pytest.fixture(scope="session")
def docker_ok() -> bool:
    return asyncio.get_event_loop().run_until_complete(_docker_works())


@pytest.mark.asyncio
async def test_sandbox_happy_path():
    if not await _docker_works():
        pytest.skip("Docker/quorum-sandbox not available")
    config.SANDBOX_DEGRADED = False
    res = await sandbox_run("print(1+1)")
    assert res["ok"] is True
    assert "2" in res["stdout"]


@pytest.mark.asyncio
async def test_sandbox_timeout_is_enforced():
    if not await _docker_works():
        pytest.skip("Docker/quorum-sandbox not available")
    config.SANDBOX_DEGRADED = False
    res = await sandbox_run("while True: pass", timeout_s=2)
    assert res["ok"] is False
    assert res.get("reason") == "timeout"


@pytest.mark.asyncio
async def test_sandbox_network_blocked():
    if not await _docker_works():
        pytest.skip("Docker/quorum-sandbox not available")
    config.SANDBOX_DEGRADED = False
    code = "import urllib.request; urllib.request.urlopen('http://example.com', timeout=3).read()"
    res = await sandbox_run(code, timeout_s=6)
    # Either non-zero exit (URLError) or we should see an error in stderr.
    assert res["ok"] is False, res


@pytest.mark.asyncio
async def test_sandbox_degraded_mode(monkeypatch):
    monkeypatch.setattr(config, "SANDBOX_DEGRADED", True)
    res = await sandbox_run("print('hi')")
    assert res["ok"] is False
    assert res["reason"] == "sandbox_offline"
