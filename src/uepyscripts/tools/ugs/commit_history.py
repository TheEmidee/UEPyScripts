"""
The Commit history: what the engine tree's git repository says about commits,
for the commands that publish, sync or clean up binaries.

`CommitHistory(root, remote)` checks that `root` is a git repository. Every
question it answers afterwards uses that one remote:
  - the current commit: Jenkins' GIT_COMMIT when set, else HEAD
  - the ancestry of the current commit, newest first. A shallow clone (CI
    checkouts usually are) is deepened from the remote first, so already
    published ancestors stay reachable; when that fails, the local history
    is used. A current commit that is still missing is refused, so nothing
    is ever published under the wrong SHA
  - whether the clone is shallow
  - the ancestry of every branch of the remote, after fetching and pruning it
  - the branch, for logs only
  - whether a folder has uncommitted changes

Failures are CommitHistoryErrors, which are WorkspaceErrors, so
`open_workspace` reports them like any other problem with the Workspace.
"""

import os
import subprocess
from pathlib import Path

from uepyscripts import logger
from uepyscripts.internal.errors import WorkspaceError

ANCESTRY_LOOKBACK = 500


class CommitHistoryError(WorkspaceError):
    """git could not answer: not a repository, git missing, or a git command failed."""


class CommitHistory:
    def __init__(self, root: Path, remote: str = "origin") -> None:
        """Raises CommitHistoryError when `root` is not in a git repository."""
        self._root = root
        self._remote = remote
        try:
            self._git("rev-parse", "--git-dir")
        except CommitHistoryError as e:
            raise CommitHistoryError(f"{root} is not a git repository ({e})") from e

    @property
    def remote(self) -> str:
        return self._remote

    def current_commit(self) -> str:
        return os.environ.get("GIT_COMMIT") or self._git("rev-parse", "HEAD")

    def ancestry(self, limit: int = ANCESTRY_LOOKBACK) -> list[str]:
        """Up to `limit` commits from the current commit back, newest first."""
        commit = self.current_commit()
        ancestry = self._log(commit, limit)

        if (ancestry is None or len(ancestry) < limit) and self.is_shallow():
            available = len(ancestry) if ancestry is not None else 0
            logger.info(f"Shallow checkout detected ({available} commit(s) available); deepening history to {limit} commits")
            if self._deepen(limit):
                ancestry = self._log(commit, limit)

        if ancestry is None:
            raise CommitHistoryError(f"The current commit {commit} (GIT_COMMIT) is not in the checkout at {self._root}")

        return ancestry

    def is_shallow(self) -> bool:
        return self._git("rev-parse", "--is-shallow-repository") == "true"

    def remote_branch_ancestries(self) -> dict[str, list[str]]:
        """Every branch of the remote, mapped to the commits reachable from its
        tip (tip first), after pruning the branches deleted on the remote."""
        remote = self._remote
        self._git("fetch", "--prune", remote)
        refs = self._git("for-each-ref", "--format=%(refname)%09%(symref)", f"refs/remotes/{remote}/").splitlines()

        ancestries: dict[str, list[str]] = {}
        for line in refs:
            ref, _, symref = line.partition("\t")
            if symref:  # refs/remotes/<remote>/HEAD points at another branch
                continue
            ancestries[ref.removeprefix(f"refs/remotes/{remote}/")] = self._git("rev-list", ref).splitlines()

        return ancestries

    def branch(self) -> str:
        """The branch being built, for logs: Jenkins' GIT_BRANCH when set,
        else the checked-out branch, else a branch pointing at a detached
        HEAD, else "HEAD"."""
        branch = os.environ.get("GIT_BRANCH")  # Jenkins' Git plugin sets this, sometimes as "origin/<branch>"
        if branch:
            return branch.split("/", 1)[1] if "/" in branch else branch

        branch = self._git("rev-parse", "--abbrev-ref", "HEAD")
        if branch != "HEAD":
            return branch

        # Detached HEAD (e.g. a CI checkout of an explicit ref rather than a
        # tracked branch, with no GIT_BRANCH env var set either): fall back to
        # whichever local or remote-tracking ref currently points at this commit.
        # Symbolic refs such as refs/remotes/origin/HEAD name no branch.
        refs = self._git("for-each-ref", "--points-at=HEAD", "--format=%(refname)%09%(symref)", "refs/heads/", "refs/remotes/").splitlines()
        for line in refs:
            ref, _, symref = line.partition("\t")
            if symref:
                continue
            if ref.startswith("refs/heads/"):
                return ref.removeprefix("refs/heads/")
            return ref.removeprefix("refs/remotes/").split("/", 1)[1]

        logger.warning("Could not resolve current branch: HEAD is detached and no ref points at it")
        return branch

    def has_uncommitted_changes(self, folder: str) -> bool:
        """Whether anything under `folder` (relative to the root) is modified or untracked."""
        return bool(self._git("status", "--porcelain", "--", folder))

    # ---- Internals ----------------------------------------------------

    def _log(self, commit: str, limit: int) -> list[str] | None:
        """The ancestry of `commit`, or None when the checkout doesn't have it."""
        known = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=self._root, capture_output=True)
        if known.returncode != 0:
            return None
        return self._git("log", f"-{limit}", "--format=%H", commit).splitlines()

    def _deepen(self, limit: int) -> bool:
        """Pulls down the commits missing from a shallow checkout, and only the
        commits: `--filter=tree:0` keeps trees and blobs on the server, so this
        stays a metadata-sized fetch even on a repository the size of an
        engine tree. Returns False (after logging) when the remote refuses."""
        try:
            self._git("fetch", "--no-tags", "--filter=tree:0", f"--deepen={limit}", self._remote)
            return True
        except CommitHistoryError as e:
            logger.warning(f"Could not deepen shallow history from '{self._remote}' ({e}); ancestry walking is limited to the local history")
            return False

    def _git(self, *args: str) -> str:
        try:
            result = subprocess.run(["git", *args], cwd=self._root, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            raise CommitHistoryError(f"git {' '.join(args)} failed: {e.stderr.strip() or e}") from e
        except OSError as e:
            raise CommitHistoryError(f"Could not run git in {self._root}: {e}") from e
        return result.stdout.strip()
