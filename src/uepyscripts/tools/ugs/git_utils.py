import os
import subprocess
from pathlib import Path

from uepyscripts import logger

ANCESTRY_LOOKBACK = 500


def get_current_sha(cwd: Path) -> str:
    sha = os.environ.get("GIT_COMMIT")  # Jenkins sets this automatically
    if sha:
        return sha
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True).strip()


def get_current_branch(cwd: Path) -> str:
    branch = os.environ.get("GIT_BRANCH")  # Jenkins' Git plugin sets this, sometimes as "origin/<branch>"
    if branch:
        return branch.split("/", 1)[1] if "/" in branch else branch

    branch = subprocess.check_output(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, text=True).strip()
    if branch != "HEAD":
        return branch

    # Detached HEAD (e.g. a CI checkout of an explicit ref rather than a
    # tracked branch, with no GIT_BRANCH env var set either) — fall back to
    # whichever local or remote-tracking ref currently points at this commit.
    refs = subprocess.check_output(
        ["git", "for-each-ref", "--points-at=HEAD", "--format=%(refname:short)", "refs/heads/", "refs/remotes/"],
        cwd=cwd,
        text=True,
    ).splitlines()
    for ref in refs:
        return ref.split("/", 1)[1] if "/" in ref else ref

    logger.warning("Could not resolve current branch: HEAD is detached and no ref points at it")
    return branch


def is_shallow_repository(cwd: Path) -> bool:
    out = subprocess.check_output(["git", "rev-parse", "--is-shallow-repository"], cwd=cwd, text=True).strip()
    return out == "true"


def deepen_shallow_history(cwd: Path, limit: int, remote: str = "origin") -> bool:
    """Pulls down the commits missing from a shallow checkout, and only the
    commits: `--filter=tree:0` keeps trees and blobs on the server, so this
    stays a metadata-sized fetch even on a repository the size of an engine
    tree. Returns False (after logging) when the remote refuses, so callers
    can carry on with whatever history is available locally."""
    try:
        subprocess.run(
            ["git", "fetch", "--no-tags", "--filter=tree:0", f"--deepen={limit}", remote],
            cwd=cwd,
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        reason = e.stderr.strip() or e
        logger.warning(f"Could not deepen shallow history from '{remote}' ({reason}); ancestry walking is limited to the local history")
        return False


def get_local_ancestry(cwd: Path, limit: int = ANCESTRY_LOOKBACK) -> list[str]:
    ancestry = _log_ancestry(cwd, limit)

    # CI checkouts are typically shallow clones (Jenkins' cloneOption(depth: 1)),
    # where HEAD is a grafted boundary commit: `git log HEAD` stops at HEAD
    # itself and every already-published parent looks unreachable, which would
    # downgrade an incremental publish into a full fresh sync. Deepen first so
    # the walk sees the real ancestry.
    if len(ancestry) < limit and is_shallow_repository(cwd):
        logger.info(f"Shallow checkout detected ({len(ancestry)} commit(s) available); deepening history to {limit} commits")
        if deepen_shallow_history(cwd, limit):
            ancestry = _log_ancestry(cwd, limit)

    return ancestry


def _log_ancestry(cwd: Path, limit: int) -> list[str]:
    out = subprocess.check_output(["git", "log", f"-{limit}", "--format=%H", "HEAD"], cwd=cwd, text=True)
    return out.splitlines()


def get_remote_branch_ancestries(cwd: Path, remote: str = "origin") -> dict[str, list[str]]:
    """Every branch on `remote`, mapped to the commits reachable from its tip
    (tip first), after pruning local remote-tracking refs for branches deleted
    on the remote."""
    subprocess.run(["git", "fetch", "--prune", remote], cwd=cwd, check=True, capture_output=True, text=True)
    refs = subprocess.check_output(
        ["git", "for-each-ref", "--format=%(refname)%09%(symref)", f"refs/remotes/{remote}/"],
        cwd=cwd,
        text=True,
    ).splitlines()

    ancestries: dict[str, list[str]] = {}
    for line in refs:
        ref, _, symref = line.partition("	")
        if symref:  # refs/remotes/origin/HEAD points at another branch
            continue
        out = subprocess.check_output(["git", "rev-list", ref], cwd=cwd, text=True)
        ancestries[ref.removeprefix(f"refs/remotes/{remote}/")] = out.splitlines()

    return ancestries
