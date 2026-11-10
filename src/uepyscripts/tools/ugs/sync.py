"""
A Sync: making the local engine tree match one Version's Manifest, from the
Publish store (see publish_store.py).

`sync_version` is the whole workflow, in this order:
  1. pick the target: the nearest Version in HEAD's ancestry, else the latest
     Version (history was rewritten, usually by a force-push)
  2. stop if the Sync state already names the target
  3. diff the target Manifest against the Sync state's
  4. download the files whose hash differs, then delete the ones that are gone
  5. save the Sync state

Local files are never hashed: they are trusted to match the Sync state. The
Sync state is only written once every file has been written, so a Sync that
fails part way is diffed against the same Sync state again next time. An
unreadable Sync state counts as no previous Sync.

Git, the command line and the S3 settings stay with the caller. PDBs are never
Tracked files, so they are never synced: debuggers get them from the symbol
store.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict, cast

from uepyscripts import logger
from uepyscripts.tools.ugs.publish_store import PublishStore
from uepyscripts.tools.ugs.ugs_types import Manifest, diff_manifests

SYNC_STATE_FILE = ".sync-state.json"


@dataclass(frozen=True)
class SyncOutcome:
    """What sync_version did. `version` is None when nothing is published yet,
    and then every other field is empty. When `already_synced`, nothing was
    downloaded or deleted."""

    version: str | None
    already_synced: bool = False
    fell_back_to_latest: bool = False
    downloaded: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)


def sync_version(store: PublishStore, root: Path, ancestry: list[str]) -> SyncOutcome:
    """Syncs the engine tree under `root`. `ancestry` is HEAD's ancestry, newest first."""
    fell_back = False
    version = store.nearest_version(ancestry)
    if version is None:
        version = store.latest_version()
        if version is None:
            return SyncOutcome(version=None)
        fell_back = True

    state_path = root / SYNC_STATE_FILE
    state = _read_sync_state(state_path)

    if state is not None and state["version"] == version:
        return SyncOutcome(version=version, already_synced=True, fell_back_to_latest=fell_back)

    target = store.manifest(version)
    to_download, to_delete = diff_manifests(state["manifest"] if state else {}, target)
    logger.info(f"Syncing to {version}: {len(to_download)} file(s) to download, {len(to_delete)} to delete")

    store.download(target, to_download, root)
    for rel in to_delete:
        (root / rel).unlink(missing_ok=True)

    _write_sync_state(state_path, {"version": version, "manifest": target})

    return SyncOutcome(version=version, fell_back_to_latest=fell_back, downloaded=to_download, deleted=to_delete)


# ---- Internals --------------------------------------------------------


class _SyncState(TypedDict):
    version: str
    manifest: Manifest


def _read_sync_state(path: Path) -> _SyncState | None:
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("version"), str) or not isinstance(data.get("manifest"), dict):
            raise ValueError("missing version or manifest")
        return cast(_SyncState, data)
    except (OSError, ValueError) as e:
        logger.warning(f"Ignoring the unreadable Sync state at {path} ({e}): every file will be downloaded")
        return None


def _write_sync_state(path: Path, state: _SyncState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))
