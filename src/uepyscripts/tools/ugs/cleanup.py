"""
Removes the Versions of the Publish store that are no longer needed (see
retention.py for the rules and publish_store.py for the Publish store). Push
never deletes anything; this is the only command that does.

Intended to run on a schedule (e.g. a periodic Jenkins job), from a full clone.
"""

import argparse
from datetime import timedelta

from uepyscripts import logger
from uepyscripts.internal.workspace import Workspace, add_uproject_argument, open_workspace
from uepyscripts.tools.ugs.commit_history import CommitHistory
from uepyscripts.tools.ugs.connection import S3_CONFIG_SECTION, add_publish_store_arguments, open_publish_store
from uepyscripts.tools.ugs.retention import retain_versions


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Delete published binaries that are no longer needed. "
            f"The S3 info is read from the [{S3_CONFIG_SECTION}] section of Config/PyScripts/config.ini, "
            "and each value can be overridden by its command line argument."
        )
    )
    add_uproject_argument(parser)
    add_publish_store_arguments(parser)
    parser.add_argument("--remote", type=str, default="origin", help="Git remote to check branches against (default: origin)")
    parser.add_argument("--keep-versions", type=int, default=30, help="Published versions to keep per remote branch (default: 30)")
    parser.add_argument(
        "--blob-grace-hours",
        type=float,
        default=24,
        help="Never delete a blob younger than this, even if no version references it (default: 24)",
    )
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Log what would be deleted without touching S3",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    logger.info("Cleanup published binaries...")

    with open_workspace(args) as workspace:
        run(workspace, args)


def run(workspace: Workspace, args: argparse.Namespace) -> None:
    history = CommitHistory(workspace.engine.root_path, remote=args.remote)
    store = open_publish_store(workspace, args, dry_run=args.dry_run)

    shallow = history.is_shallow()
    logger.info(f"Fetching '{history.remote}' and computing the ancestry of each branch")
    branch_ancestries = history.remote_branch_ancestries()

    outcome = retain_versions(
        store,
        branch_ancestries,
        shallow=shallow,
        keep=args.keep_versions,
        blob_grace=timedelta(hours=args.blob_grace_hours),
    )

    prefix = "[dry-run] Would have removed" if args.dry_run else "Removed"
    logger.info(f"{prefix} {len(outcome.removed_versions)} version(s) and {outcome.deleted_blobs} blob(s).")


if __name__ == "__main__":
    main()
