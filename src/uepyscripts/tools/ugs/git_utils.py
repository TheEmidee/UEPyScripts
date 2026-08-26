import os
import subprocess
from pathlib import Path

ANCESTRY_LOOKBACK = 2000


def get_current_sha(cwd: Path) -> str:
    sha = os.environ.get("GIT_COMMIT")  # Jenkins sets this automatically
    if sha:
        return sha
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True).strip()


def get_current_branch(cwd: Path) -> str:
    branch = os.environ.get("GIT_BRANCH")  # Jenkins' Git plugin sets this, sometimes as "origin/<branch>"
    if branch:
        return branch.split("/", 1)[1] if "/" in branch else branch
    return subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, text=True).strip()


def get_local_ancestry(cwd: Path, limit: int = ANCESTRY_LOOKBACK) -> list[str]:
    out = subprocess.check_output(["git", "log", f"-{limit}", "--format=%H", "HEAD"], cwd=cwd, text=True)
    return out.splitlines()


def get_remote_reachable_shas(cwd: Path, remote: str = "origin") -> set[str]:
    """All commit SHAs reachable from any current branch tip on `remote`, after
    pruning local remote-tracking refs for branches deleted on the remote."""
    subprocess.run(["git", "fetch", "--prune", remote], cwd=cwd, check=True, capture_output=True, text=True)
    out = subprocess.check_output(["git", "rev-list", f"--remotes={remote}"], cwd=cwd, text=True)
    return set(out.splitlines())


def resolve_nearest_published_ancestor(index: list[str], ancestry: list[str]) -> tuple[str | None, bool]:
    """Finds the nearest ancestor SHA (including HEAD itself) present in the
    index. Returns None if nothing has ever been published reachable from HEAD
    within the walked ancestry. The bool is True when the match was found by
    walking the ancestry itself (an exact match), False when falling back to
    the most recent published version because nothing in the ancestry matched."""
    index_set = set(index)
    for sha in ancestry:
        if sha in index_set:
            return sha, True

    if index:
        return index[-1], False

    return None, True
