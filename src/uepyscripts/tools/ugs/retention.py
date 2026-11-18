"""
Retention: deciding which Versions stay in the Publish store (see
publish_store.py) and removing the rest. Nothing else ever deletes from it.

`retain_versions` is the whole workflow, in this order:
  1. refuse, before touching the Publish store, when the history is shallow
     (published commits beyond its depth would look unreachable and get
     deleted), when the remote has no branches, or when fewer than one
     Version per branch would be kept
  2. keep the newest `keep` Versions along each branch's ancestry, tip first.
     Commits that aren't Versions don't count towards `keep`
  3. remove every other Version: the ones beyond that window, and the ones no
     branch reaches any more (their branch was deleted)
  4. delete every Blob no remaining Version references, once it is older than
     `blob_grace`, so the Blobs of a push still in progress survive

This needs no per-branch bookkeeping in the Publish store: it is computed
straight from the branch ancestries. Git and the command line stay with the
caller, and so do dry runs: a dry run is a Publish store over DryRunStorage.
"""

from dataclasses import dataclass
from datetime import timedelta

from uepyscripts import logger
from uepyscripts.internal.errors import WorkspaceError
from uepyscripts.tools.ugs.publish_store import PublishStore


class RetentionRefusedError(WorkspaceError):
    """Retention refused to run, and nothing was deleted."""


@dataclass(frozen=True)
class RetentionOutcome:
    """What retain_versions did. `published` are the Versions it found, `kept`
    the ones it left, `removed_versions` the ones it removed."""

    published: set[str]
    kept: set[str]
    removed_versions: list[str]
    deleted_blobs: int


def retain_versions(
    store: PublishStore,
    branch_ancestries: dict[str, list[str]],
    *,
    shallow: bool,
    keep: int,
    blob_grace: timedelta,
) -> RetentionOutcome:
    """Keeps the newest `keep` Versions along each branch and removes the rest.

    `branch_ancestries` maps every branch of the remote to the commits
    reachable from its tip, tip first. `shallow` is whether that history comes
    from a shallow clone. Raises RetentionRefusedError, without touching the
    Publish store, when the history is shallow, there is no branch, or `keep`
    is below 1."""
    if shallow:
        raise RetentionRefusedError(
            "This is a shallow clone: published commits beyond its depth would look unreachable and get deleted. Run from a full clone."
        )
    if not branch_ancestries:
        raise RetentionRefusedError("The remote has no branch: aborting without deleting anything")
    if keep < 1:
        raise RetentionRefusedError(f"Keep at least one Version per branch (asked for {keep})")

    published = store.versions()
    kept = _versions_to_keep(published, branch_ancestries, keep)
    to_remove = published - kept

    logger.info(f"{len(published)} published version(s): keeping {len(kept)}, removing {len(to_remove)}")

    result = store.prune(to_remove, blob_grace=blob_grace)

    return RetentionOutcome(published=published, kept=kept, removed_versions=result.removed_versions, deleted_blobs=result.deleted_blobs)


# ---- Internals --------------------------------------------------------


def _versions_to_keep(published: set[str], branch_ancestries: dict[str, list[str]], keep: int) -> set[str]:
    kept: set[str] = set()
    for ancestry in branch_ancestries.values():
        on_branch = [sha for sha in ancestry if sha in published]
        kept.update(on_branch[:keep])
    return kept
