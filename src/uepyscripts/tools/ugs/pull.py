"""
Syncs local engine + game binaries to match the current git HEAD (or its
nearest published ancestor commit), from the Publish store (see
publish_store.py).

  - Walks HEAD's ancestry and picks the nearest commit that has a Manifest.
  - Compares that Manifest with the one recorded by the previous sync in
    .sync-state.json (at the engine root), downloads only the files whose hash
    differs and deletes the ones that are gone. Local files are never hashed:
    they are assumed to still match the previous sync.
  - Without a previous sync, every file of the target Manifest is downloaded.
  - PDB files are never downloaded here — they are served on-demand via the
    symbol store instead. Configure your debugger's symbol path separately.
"""

import argparse
import json
import subprocess
from pathlib import Path
from typing import TypedDict

from uepyscripts import logger
from uepyscripts.internal.engine import resolve_engine
from uepyscripts.internal.project import resolve_project
from uepyscripts.tools.ugs.git_utils import get_local_ancestry
from uepyscripts.tools.ugs.publish_store import DEFAULT_JOBS, PublishStore
from uepyscripts.tools.ugs.s3_settings import S3_CONFIG_SECTION, add_s3_arguments, resolve_s3_settings
from uepyscripts.tools.ugs.ugs_types import Manifest

# ---- CONFIG ----------------------------------------------------------

LOCAL_STATE_FILE = ".sync-state.json"  # {"version": ..., "manifest": {...}}, relative to the engine root


class LocalState(TypedDict):
    version: str | None
    manifest: Manifest


class LocalStateManager:
    def __init__(self, root_folder: Path) -> None:
        self.path = root_folder / LOCAL_STATE_FILE
        self.data: LocalState = LocalState(version=None, manifest={})

        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))


def compute_sync(local: Manifest, target: Manifest) -> tuple[list[str], list[str]]:
    """Files to download and files to delete to go from `local` to `target`."""
    to_download = [p for p, h in target.items() if local.get(p) != h]
    to_delete = [p for p in local if p not in target]
    return to_download, to_delete


def warn_if_source_dirty(root_folder: Path) -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "Engine/Source"],
        cwd=root_folder,
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        logger.warning(
            "You have uncommitted changes under Engine/Source (or the game project's "
            "Source folder). Synced binaries reflect the last committed state only — "
            "you'll likely need to rebuild before your local changes take effect."
        )


def sync(store: PublishStore, root_folder: Path, target_version: str, state: LocalState) -> LocalState:
    logger.info("=== Start syncing binaries ===")

    target = store.manifest(target_version)
    to_download, to_delete = compute_sync(state.get("manifest", {}), target)

    logger.info(f"{len(to_download)} file(s) to download, {len(to_delete)} to delete")

    store.download(target, to_download, root_folder)

    for rel in to_delete:
        (root_folder / rel).unlink(missing_ok=True)

    logger.info(f"=== Finished syncing. Now at {target_version} ===")
    return LocalState(version=target_version, manifest=target)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Sync local engine + game binaries to match the current git HEAD. "
            f"The S3 info is read from the [{S3_CONFIG_SECTION}] section of Config/PyScripts/config.ini, "
            "and each value can be overridden by its command line argument."
        )
    )
    parser.add_argument("--uproject-path", type=Path, help=("Path to a native uproject file"))
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help=f"Number of parallel downloads (default: {DEFAULT_JOBS})")
    add_s3_arguments(parser)

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    logger.info("Syncing binaries...")

    try:
        project = resolve_project(args.uproject_path)
    except Exception as e:
        logger.fatal(f"Project resolution failed: {e}")
        exit(1)

    if not project.is_native_project:
        logger.fatal("You can only sync binaries for native projects")
        exit(1)

    engine = resolve_engine(project)

    s3_settings = resolve_s3_settings(project, args)
    store = PublishStore.from_settings(s3_settings, jobs=args.jobs)

    root_folder = engine.root_path
    local_state = LocalStateManager(root_folder)

    warn_if_source_dirty(root_folder)

    ancestry = get_local_ancestry(root_folder)
    target_version = store.nearest_version(ancestry)

    if target_version is None:
        target_version = store.latest_version()

        if target_version is None:
            logger.info("Nothing has been published yet — nothing to sync.")
            return

        logger.warning(
            f"No commit in HEAD's ancestry matches a published version — this usually means "
            f"history was rewritten on the published branch (a force-push). Falling back to "
            f"the latest published version ({target_version[:8]}), which may not exactly "
            f"match your current source. You may need a local rebuild."
        )

    if local_state.data.get("version") == target_version:
        logger.info(f"Already up to date ({target_version})")
        return

    logger.info(f"Will sync up to {target_version}")

    local_state.data = sync(store, root_folder, target_version, local_state.data)
    local_state.save()


if __name__ == "__main__":
    main()
