import subprocess

from uepyscripts import logger


def run_subprocess(cmd: list[str], log_output: bool = True) -> int:
    """Run a subprocess with the given command and return the Popen object."""
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True, bufsize=1, universal_newlines=True)

    assert process.stdout is not None
    assert process.stderr is not None

    if log_output:
        for line in process.stdout:
            line = line.strip()
            if line:
                logger.info(line)

    process.wait()
    return process.returncode
