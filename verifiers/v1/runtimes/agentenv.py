import os
import shlex
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import Field
from pydantic_config import BaseConfig

from verifiers.v1.errors import SandboxError
from verifiers.v1.runtimes.base import BaseRuntimeInfo, ProgramResult, Runtime
from verifiers.v1.utils.aio import run_shielded

if TYPE_CHECKING:
    from e2b import AsyncSandbox
    from e2b.connection_config import ApiParams


class AgentEnvConfig(BaseConfig):
    type: Literal["agentenv"] = "agentenv"
    api_url: str = "http://127.0.0.1:8000"
    snapshot: str
    workdir: str = "/app"
    timeout: int = Field(default=1800, gt=0)


class AgentEnvRuntimeInfo(AgentEnvConfig, BaseRuntimeInfo):
    pass


class AgentEnvRuntime(Runtime):
    is_local: ClassVar[bool] = False

    def __init__(self, config: AgentEnvConfig, name: str | None = None) -> None:
        super().__init__(name)
        self.config = config
        self.info = AgentEnvRuntimeInfo(**config.model_dump())
        self._sandbox: AsyncSandbox
        self._released = False
        self._api: ApiParams = {
            "api_url": config.api_url,
            "sandbox_url": config.api_url,
            "api_key": os.environ["E2B_API_KEY"],
        }

    async def start(self) -> None:
        from e2b import AsyncSandbox

        async def create() -> None:
            self._sandbox = await AsyncSandbox.create(
                self.config.snapshot,
                timeout=self.config.timeout,
                metadata={"name": self.name},
                **self._api,
            )
            self.info.id = self._sandbox.sandbox_id

        try:
            await run_shielded(create())
            await self._sandbox.commands.run(
                shlex.join(["mkdir", "-p", self.config.workdir])
            )
        except Exception as error:
            raise SandboxError(f"agentenv provisioning failed: {error}") from error

    async def run(self, argv: list[str], env: dict[str, str]) -> ProgramResult:
        from e2b import CommandExitException

        try:
            result = await self._sandbox.commands.run(
                shlex.join(argv),
                cwd=self.config.workdir,
                envs=self.process_env(env),
                timeout=0,
            )
        except CommandExitException as error:
            return ProgramResult(error.exit_code, error.stdout, error.stderr)
        except Exception as error:
            raise SandboxError(f"agentenv exec failed: {error}") from error
        return ProgramResult(result.exit_code, result.stdout, result.stderr)

    async def run_background(
        self, argv: list[str], env: dict[str, str], log: str
    ) -> None:
        try:
            process = await self._sandbox.commands.run(
                f"exec {shlex.join(argv)} > {shlex.quote(log)} 2>&1",
                background=True,
                cwd=self.config.workdir,
                envs=self.process_env(env),
                timeout=0,
            )
            await process.disconnect()
        except Exception as error:
            raise SandboxError(f"agentenv background launch failed: {error}") from error

    async def _read(self, path: str, max_bytes: int | None = None) -> bytes:
        if max_bytes is not None:
            return await super()._read(path, max_bytes)
        try:
            return bytes(
                await self._sandbox.files.read(
                    str(PurePosixPath(self.config.workdir) / path), format="bytes"
                )
            )
        except Exception as error:
            raise SandboxError(f"read {path!r}: {error}") from error

    async def write(self, path: str, data: bytes) -> None:
        try:
            await self._sandbox.files.write(
                str(PurePosixPath(self.config.workdir) / path), data
            )
        except Exception as error:
            raise SandboxError(f"write {path!r}: {error}") from error

    def cleanup(self) -> None:
        if self.info.id is not None and not self._released:
            from e2b import Sandbox

            Sandbox.kill(self.info.id, **self._api)
            self._released = True
