"""
How Engine tools get launched.

`ProcessRunner` is the seam: `Engine` only ever asks it to run a program and
wait for its exit code, or to start one in the background. `PopenRunner` is
the production adapter; tests use a recorder that captures the argv instead.

Executables are never checked before launching: right after cloning, an
Engine tool such as UnrealBuildTool.exe may legitimately not exist yet. Only
when the OS refuses to start the program does it become an
EngineToolNotStartedError.
"""

import subprocess
import sys
from typing import Any, Protocol

from uepyscripts import logger
from uepyscripts.internal.errors import WorkspaceError


class EngineToolNotStartedError(WorkspaceError):
    """The OS could not start an Engine tool, usually because it hasn't been built yet."""

    def __init__(self, executable: str) -> None:
        self.executable = executable
        super().__init__(f"Could not start {executable}: it does not exist. The engine may need to be built first.")


class ProcessRunner(Protocol):
    def run(self, argv: list[str]) -> int:
        """Run the program, stream its output to the log, and return its exit code."""
        ...

    def start(self, argv: list[str]) -> None:
        """Start the program in the background, without waiting for it."""
        ...


class PopenRunner:
    """Launches real processes in their own process group, with no console window."""

    def run(self, argv: list[str]) -> int:
        logger.debug(f"Run {argv}")
        process = self._popen(argv, capture_output=True)

        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if line:
                logger.info(line)

        process.wait()
        return process.returncode

    def start(self, argv: list[str]) -> None:
        logger.debug(f"Start {argv}")
        self._popen(argv, capture_output=False)

    def _popen(self, argv: list[str], capture_output: bool) -> "subprocess.Popen[str]":
        """With capture_output, stdout and stderr are merged into a line-buffered text pipe;
        otherwise the process is fully detached from ours (no stdin, stdout or stderr)."""
        platform_kwargs: dict[str, Any] = {}
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            platform_kwargs["startupinfo"] = startupinfo
            platform_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        else:
            platform_kwargs["start_new_session"] = True

        try:
            if capture_output:
                return subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, **platform_kwargs)

            return subprocess.Popen(
                argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, **platform_kwargs
            )
        except FileNotFoundError as e:
            raise EngineToolNotStartedError(argv[0]) from e
