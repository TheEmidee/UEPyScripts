"""
Syncs the local engine + game binaries to the current git HEAD, or to its
nearest published ancestor, from the Publish store (see sync.py for the
workflow and publish_store.py for the Publish store).

PDB files are never downloaded here: they are served on demand by the symbol
store. Configure your debugger's symbol path separately.
"""

import argparse
import subprocess
from pathlib import Path

from uepyscripts import logger
from uepyscripts.internal.workspace import Workspace, add_uproject_argument, open_workspace
from uepyscripts.tools.ugs.connection import S3_CONFIG_SECTION, add_publish_store_arguments, open_publish_store
from uepyscripts.tools.ugs.git_utils import get_local_ancestry
from uepyscripts.tools.ugs.sync import sync_version


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


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Sync local engine + game binaries to match the current git HEAD. "
            f"The S3 info is read from the [{S3_CONFIG_SECTION}] section of Config/PyScripts/config.ini, "
            "and each value can be overridden by its command line argument."
        )
    )
    add_uproject_argument(parser)
    add_publish_store_arguments(parser)

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    logger.info("Syncing binaries...")

    with open_workspace(args) as workspace:
        run(workspace, args)


def run(workspace: Workspace, args: argparse.Namespace) -> None:
    store = open_publish_store(workspace, args)
    root_folder = workspace.engine.root_path
    warn_if_source_dirty(root_folder)

    outcome = sync_version(store, root_folder, get_local_ancestry(root_folder))

    if outcome.version is None:
        logger.info("Nothing has been published yet — nothing to sync.")
        return

    if outcome.fell_back_to_latest:
        logger.warning(
            f"No commit in HEAD's ancestry matches a published version — this usually means "
            f"history was rewritten on the published branch (a force-push). Using "
            f"the latest published version ({outcome.version[:8]}), which may not exactly "
            f"match your current source. You may need a local rebuild."
        )

    if outcome.already_synced:
        logger.info(f"Already up to date ({outcome.version})")
        return

    logger.info(f"Synced to {outcome.version}: {len(outcome.downloaded)} file(s) downloaded, {len(outcome.deleted)} deleted")


if __name__ == "__main__":
    main()
