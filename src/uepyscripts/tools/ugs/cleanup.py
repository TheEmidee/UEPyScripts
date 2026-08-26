"""
Prunes S3 data for commits whose branch no longer exists on the remote.

  - A commit is "orphaned" once it is no longer reachable from any current
    remote branch tip (i.e. its branch was deleted). This needs no per-branch
    bookkeeping in S3 — reachability is computed straight from git, the same
    way push.py/pull.py resolve diff baselines and sync targets.
  - Deletes manifests/{sha}.json, deltas/{sha}.7z and checkpoints/{sha}.7z for
    every orphaned sha, then rewrites index.json/checkpoints.json to drop them.
  - Intended to run on a schedule (e.g. a periodic Jenkins job).
"""

import argparse
import json
from pathlib import Path
from typing import cast

from gamedevtools.s3 import S3Client

from uepyscripts import logger
from uepyscripts.internal.engine import resolve_engine
from uepyscripts.internal.project import resolve_project
from uepyscripts.tools.ugs.git_utils import get_remote_reachable_shas


class Context:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.s3_client: S3Client = S3Client(
            access_key=args.s3_access_key,
            secret_key=args.s3_secret_key,
            region=args.s3_bucket_region,
        )


def build_orphaned_keys(orphaned: list[str]) -> list[str]:
    """S3 keys to delete for each orphaned sha. Including a key that was never
    written is harmless — S3 batch-delete is a no-op for missing keys, the same
    assumption prune_old_versions (push.py) already relies on."""
    keys: list[str] = []
    for sha in orphaned:
        keys.append(f"manifests/{sha}.json")
        keys.append(f"deltas/{sha}.7z")
        keys.append(f"checkpoints/{sha}.7z")
    return keys


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Delete S3 binary-publish data for branches that no longer exist on the remote.")
    parser.add_argument("--uproject-path", type=Path, help=("Path to a native uproject file"))
    parser.add_argument("--s3-bucket-name", type=str, help=("AWS S3 Bucket Name"))
    parser.add_argument("--s3-bucket-region", type=str, help=("AWS S3 Bucket Region"))
    parser.add_argument("--s3-access-key", type=str, help=("AWS S3 Access Key"))
    parser.add_argument("--s3-secret-key", type=str, help=("AWS S3 Secret Key"))
    parser.add_argument("--remote", type=str, default="origin", help="Git remote to check branches against (default: origin)")
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Log what would be deleted without touching S3",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    logger.info("Cleanup orphaned binary publishes...")

    try:
        project = resolve_project(args.uproject_path)
    except Exception as e:
        logger.fatal(f"Project resolution failed: {e}")
        exit(1)

    engine = resolve_engine(project)
    context = Context(args)

    logger.info(f"Fetching '{args.remote}' and computing reachable commits")
    reachable = get_remote_reachable_shas(engine.root_path, args.remote)

    if not reachable:
        logger.fatal(f"No commit is reachable from any branch on remote '{args.remote}' — aborting without deleting anything")
        exit(1)

    logger.info("Download index.json")
    index = cast(list[str], context.s3_client.download_json(context.args.s3_bucket_name, "index.json", default=[]))

    logger.info("Download checkpoints.json")
    checkpoints = cast(list[str], context.s3_client.download_json(context.args.s3_bucket_name, "checkpoints.json", default=[]))

    orphaned = [sha for sha in index if sha not in reachable]

    if not orphaned:
        logger.info(f"Nothing to clean up. {len(index)} published commit(s), all reachable from '{args.remote}'.")
        return

    logger.info(f"Found {len(orphaned)} orphaned commit(s) out of {len(index)} published")

    keys = build_orphaned_keys(orphaned)

    if args.dry_run:
        logger.info(f"[dry-run] Would delete {len(keys)} key(s):")
        for key in keys:
            logger.info(f"[dry-run]   {key}")
        return

    context.s3_client.delete_keys(context.args.s3_bucket_name, keys)

    orphaned_set = set(orphaned)
    index = [sha for sha in index if sha not in orphaned_set]
    checkpoints = [sha for sha in checkpoints if sha not in orphaned_set]

    logger.info("Upload index.json")
    context.s3_client.upload_bytes(context.args.s3_bucket_name, "index.json", json.dumps(index).encode(), content_type="application/json")

    logger.info("Upload checkpoints.json")
    context.s3_client.upload_bytes(
        context.args.s3_bucket_name, "checkpoints.json", json.dumps(checkpoints).encode(), content_type="application/json"
    )

    logger.info(f"Cleanup done. Deleted {len(keys)} key(s) for {len(orphaned)} orphaned commit(s).")


if __name__ == "__main__":
    main()
