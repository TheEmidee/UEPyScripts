import subprocess
import sys
from typing import Any

from uepyscripts import logger


def run_subprocess(cmd: list[str], log_output: bool = True) -> int:
    """Run a subprocess with the given command and return its exit code (or 0 if fire-and-forget)."""
    kwargs: dict[str, Any] = {}
    creationflags = 0

    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    else:
        kwargs["start_new_session"] = True

    if log_output:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=creationflags,
            **kwargs,
        )

        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if line:
                logger.info(line)

        process.wait()
        return process.returncode
    else:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            **kwargs,
        )
        return 0
