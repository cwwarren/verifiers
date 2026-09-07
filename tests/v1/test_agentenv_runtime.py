import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from verifiers.v1.runtimes import AgentEnvConfig, provision_runtime

e2b = pytest.importorskip("e2b")


@pytest.mark.asyncio
async def test_cancelled_creation_releases_the_allocated_sandbox(monkeypatch):
    allocated = asyncio.Event()
    complete = asyncio.Event()
    live = set()
    sandbox = SimpleNamespace(
        sandbox_id="allocated-sandbox",
        commands=SimpleNamespace(run=AsyncMock()),
    )

    async def create(*args, **kwargs):
        live.add(sandbox.sandbox_id)
        allocated.set()
        await complete.wait()
        return sandbox

    def kill(sandbox_id, **kwargs):
        live.remove(sandbox_id)
        return True

    monkeypatch.setenv("E2B_API_KEY", "test")
    monkeypatch.setattr(e2b.AsyncSandbox, "create", create)
    monkeypatch.setattr(e2b.Sandbox, "kill", kill)

    async def episode():
        async with provision_runtime(AgentEnvConfig(snapshot="snapshot")):
            raise AssertionError("Cancelled allocation reached the actor")

    pending = asyncio.create_task(episode())
    await allocated.wait()
    pending.cancel()
    complete.set()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert not live
