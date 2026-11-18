"""
Syncs the local engine + game binaries to the current git HEAD, or to its
nearest published ancestor, from the Publish store (see sync.py for the
workflow and publish_store.py for the Publish store).

PDB files are only downloaded when the [UGS] SyncSymbols config key is set,
and only for Versions pushed with --upload-symbols-to-s3. Otherwise they are
served on demand by the symbol store: configure your debugger's symbol path
separately.
"""

import argparse

from uepyscripts import logger
from uepyscripts.internal.workspace import Workspace, add_uproject_argument, open_workspace
from uepyscripts.tools.ugs.commit_history import CommitHistory
from uepyscripts.tools.ugs.connection import S3_CONFIG_SECTION, add_publish_store_arguments, open_publish_store
from uepyscripts.tools.ugs.sync import sync_version


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
    root_folder = workspace.engine.root_path
    history = CommitHistory(root_folder)
    store = open_publish_store(workspace, args)

    if history.has_uncommitted_changes("Engine/Source"):
        logger.warning(
            "You have uncommitted changes under Engine/Source. Synced binaries reflect the last committed state only — "
            "you'll likely need to rebuild before your local changes take effect."
        )

    sync_symbols = workspace.config.ugs.sync_symbols
    if sync_symbols:
        logger.info("Symbol files will be synced too ([UGS] SyncSymbols)")

    outcome = sync_version(store, root_folder, history.ancestry(), with_symbols=sync_symbols)

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

    if sync_symbols and not outcome.with_symbols:
        logger.warning(f"{outcome.version[:8]} was published without symbol files (push without --upload-symbols-to-s3): none synced")

    if outcome.already_synced:
        logger.info(f"Already up to date ({outcome.version})")
        return

    logger.info(f"Synced to {outcome.version}: {len(outcome.downloaded)} file(s) downloaded, {len(outcome.deleted)} deleted")


if __name__ == "__main__":
    main()
