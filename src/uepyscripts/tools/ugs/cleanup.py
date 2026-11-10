"""
Retention for the Publish store (see publish_store.py). Push never deletes
anything; this is the only place that does.

  - Keeps the newest --keep-versions Versions along each remote branch's
    ancestry. Every other Version is removed: the ones beyond that window,
    and the ones no current remote branch can reach (their branch was
    deleted). This needs no per-branch bookkeeping in the bucket — it is
    computed straight from git.
  - Then deletes every Blob no remaining Manifest references, once it is older
    than --blob-grace-hours (so Blobs of a push still in progress survive).
  - Intended to run on a schedule (e.g. a periodic Jenkins job).
"""

import argparse
from datetime import timedelta
from pathlib import Path

from uepyscripts import logger
from uepyscripts.internal.engine import resolve_engine
from uepyscripts.internal.project import resolve_project
from uepyscripts.tools.ugs.git_utils import get_remote_branch_ancestries, is_shallow_repository
from uepyscripts.tools.ugs.publish_store import DEFAULT_JOBS, PublishStore
from uepyscripts.tools.ugs.s3_settings import S3_CONFIG_SECTION, add_s3_arguments, resolve_s3_settings


def select_versions_to_keep(published: set[str], branch_ancestries: dict[str, list[str]], keep: int) -> set[str]:
    """The newest `keep` published commits along each branch's ancestry (tip first)."""
    kept: set[str] = set()
    for ancestry in branch_ancestries.values():
        on_branch = [sha for sha in ancestry if sha in published]
        kept.update(on_branch[:keep])
    return kept


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Delete published binaries that are no longer needed. "
            f"The S3 info is read from the [{S3_CONFIG_SECTION}] section of Config/PyScripts/config.ini, "
            "and each value can be overridden by its command line argument."
        )
    )
    parser.add_argument("--uproject-path", type=Path, help=("Path to a native uproject file"))
    add_s3_arguments(parser)
    parser.add_argument("--remote", type=str, default="origin", help="Git remote to check branches against (default: origin)")
    parser.add_argument("--keep-versions", type=int, default=30, help="Published versions to keep per remote branch (default: 30)")
    parser.add_argument(
        "--blob-grace-hours",
        type=float,
        default=24,
        help="Never delete a blob younger than this, even if no version references it (default: 24)",
    )
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help=f"Number of parallel manifest downloads (default: {DEFAULT_JOBS})")
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

    try:
        project = resolve_project(args.uproject_path)
    except Exception as e:
        logger.fatal(f"Project resolution failed: {e}")
        exit(1)

    if not project.is_native_project:
        logger.fatal("You can only clean up binaries for native projects")
        exit(1)

    engine = resolve_engine(project)

    if is_shallow_repository(engine.root_path):
        logger.fatal("This is a shallow clone: published commits beyond its depth would look unreachable and get deleted. Run from a full clone.")
        exit(1)

    s3_settings = resolve_s3_settings(project, args)
    store = PublishStore.from_settings(s3_settings, jobs=args.jobs, dry_run=args.dry_run)

    logger.info(f"Fetching '{args.remote}' and computing the ancestry of each branch")
    branch_ancestries = get_remote_branch_ancestries(engine.root_path, args.remote)

    if not branch_ancestries:
        logger.fatal(f"No branch found on remote '{args.remote}' — aborting without deleting anything")
        exit(1)

    published = store.versions()
    kept = select_versions_to_keep(published, branch_ancestries, args.keep_versions)
    to_remove = published - kept

    logger.info(f"{len(published)} published version(s): keeping {len(kept)}, removing {len(to_remove)}")

    result = store.prune(to_remove, blob_grace=timedelta(hours=args.blob_grace_hours))

    prefix = "[dry-run] Would have removed" if args.dry_run else "Removed"
    logger.info(f"{prefix} {len(result.removed_versions)} version(s) and {result.deleted_blobs} blob(s).")


if __name__ == "__main__":
    main()
