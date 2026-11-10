"""
Publishes the engine + game binaries of the current commit as a Version (see
publish.py for the workflow and publish_store.py for the Publish store):
  - the Tracked files are hashed, every content the bucket doesn't have yet is
    uploaded as a Blob, then the Manifest of the current commit is written
  - PDB/DLL/EXE files are additionally indexed into a Windows symbol store
  - Versions are keyed by git commit SHA (no git push required)
  - Retention is handled by ugs.cleanup, never here

The list of changed files is written to Engine/Saved/changed_files.txt.
"""

import argparse

from uepyscripts import logger
from uepyscripts.internal.workspace import Workspace, add_uproject_argument, open_workspace
from uepyscripts.tools.ugs.git_utils import get_current_branch, get_current_sha, get_local_ancestry
from uepyscripts.tools.ugs.publish import DEFAULT_KEEP_HASH_CACHES, ENGINE_TRACKED_FILES, SymbolIndexer, SymStoreIndexer, publish_version
from uepyscripts.tools.ugs.publish_store import DEFAULT_JOBS, PublishStore
from uepyscripts.tools.ugs.s3_settings import S3_CONFIG_SECTION, add_s3_arguments, resolve_s3_settings


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Publish the engine + game binaries for the current git HEAD. "
            f"The S3 info is read from the [{S3_CONFIG_SECTION}] section of Config/PyScripts/config.ini, "
            "and each value can be overridden by its command line argument."
        )
    )
    add_uproject_argument(parser)
    parser.add_argument(
        "--skip-upload",
        action=argparse.BooleanOptionalAction,
        help=("Scan and write Engine/Saved/changed_files.txt, but don't upload anything or update the symbol store"),
    )
    add_s3_arguments(parser)
    parser.add_argument("--disable-symbol-store-upload", action=argparse.BooleanOptionalAction)
    parser.add_argument("--symbol-store-path", type=str, help=("Path of the shared symbol store folder"))
    parser.add_argument(
        "--keep_hash_caches",
        type=int,
        default=DEFAULT_KEEP_HASH_CACHES,
        help=f"Number of hash caches to retain in the bucket; older ones get deleted (default: {DEFAULT_KEEP_HASH_CACHES})",
    )
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help=f"Number of parallel uploads (default: {DEFAULT_JOBS})")

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    logger.info("Publish binaries...")

    with open_workspace(args) as workspace:
        run(workspace, args)


def run(workspace: Workspace, args: argparse.Namespace) -> None:
    project = workspace.project

    if not project.is_native_project:
        logger.fatal("You can only publish binaries for native projects")
        exit(1)

    symbol_indexer: SymbolIndexer | None = None
    if args.disable_symbol_store_upload:
        logger.info("Upload on the symbol store is disabled")
    elif not args.symbol_store_path:
        logger.fatal("Pass --symbol-store-path, or --disable-symbol-store-upload to skip the symbol store")
        exit(1)
    else:
        symbol_indexer = SymStoreIndexer(args.symbol_store_path, project.project_name)

    engine = workspace.engine

    s3_settings = resolve_s3_settings(workspace.config, args)
    store = PublishStore.from_settings(s3_settings, jobs=args.jobs)

    root = engine.root_path
    commit = get_current_sha(root)

    logger.info("=== Publish binary files ===")
    logger.info(f"Current branch: {get_current_branch(root)}")

    outcome = publish_version(
        store,
        ENGINE_TRACKED_FILES,
        root,
        commit,
        get_local_ancestry(root),
        symbol_indexer=symbol_indexer,
        skip_upload=bool(args.skip_upload),
        keep_hash_caches=args.keep_hash_caches,
    )

    if outcome.already_published:
        logger.info(f"{commit} already published, skipping (likely a CI re-run of an already-built commit)")
        return

    logger.info("Saving list of changed files in Engine/Saved/changed_files.txt")
    changed_files_path = engine.saved_path.joinpath("changed_files.txt").resolve()
    changed_files_path.parent.mkdir(parents=True, exist_ok=True)
    changed_files_path.write_text("\n".join(outcome.changed))

    if args.skip_upload:
        logger.info("Skipped the upload (--skip-upload)")
        return

    logger.info(f"Published {commit}: {outcome.uploaded_blobs} new blob(s), {outcome.reused_blobs} reused")
    logger.info("=== Finished processing binary files ===")


if __name__ == "__main__":
    main()
