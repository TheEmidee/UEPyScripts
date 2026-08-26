import argparse
import json
import subprocess
import tempfile
from pathlib import Path
from typing import TypedDict

from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from gamedevtools.s3 import S3Client

from uepyscripts import logger
from uepyscripts.internal.engine import resolve_engine
from uepyscripts.internal.project import resolve_project
from uepyscripts.tools.ugs.git_utils import get_local_ancestry, resolve_nearest_published_ancestor
from uepyscripts.tools.ugs.ugs_types import Manifest, VersionManifest

"""
Syncs local engine + game binaries to match the current git HEAD (or nearest
published ancestor commit), as a single unified stream (no engine/game split).

  - index.json (a list of commit SHAs that have a publish) doubles as the
    record of "which commits have a publish" — resolution walks HEAD's
    ancestry and finds the nearest SHA present in it.
  - Jumps to the newest applicable checkpoint (full state) if one exists
    between the client's current version and the target, then replays any
    remaining deltas on top.
  - Every archive is extracted relative to the common root shared by the
    engine and project folders, so paths land correctly whether they
    originated from Engine/ or the game project.
  - PDB files are never downloaded here — they're excluded from the
    delta/checkpoint pipeline entirely and served on-demand via the
    symbol store instead. Configure your debugger's symbol path separately.

Requires 7z.exe on PATH (or set SEVEN_ZIP_PATH below).
"""

# ---- CONFIG ----------------------------------------------------------
LOCAL_STATE_FILE = ".sync-state.json"  # {"version": ..., "manifest": {...}}


class LocalState(TypedDict):
    version: str | None
    manifest: dict[str, str]


class Context:
    def __init__(self, root_folder: Path, args: argparse.Namespace) -> None:
        self.root_folder: Path = root_folder
        self.s3_bucket_name: str = args.s3_bucket_name
        self.s3_bucket_region: str = args.s3_bucket_region
        self.s3_client: S3Client = S3Client(
            access_key=args.s3_access_key,
            secret_key=args.s3_secret_key,
            region=args.s3_bucket_region,
        )
        logger.info("Download index.json")
        self.commit_index = self.s3_client.download_json(self.s3_bucket_name, "index.json", default=[])


class LocalStateManager:
    def __init__(self) -> None:
        self.path = Path(LOCAL_STATE_FILE)
        self.data: LocalState = LocalState(version=None, manifest={})

        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))


def download_and_extract_archive(context: Context, s3_file_path: str) -> None:
    """Downloads and extracts a .7z archive into the context root folder
    — so relative paths for both engine and game files land correctly."""
    logger.info(f"Download archive {s3_file_path}")
    archive_bytes = context.s3_client.download_bytes(context.s3_bucket_name, s3_file_path)

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / "archive.7z"
        archive_path.write_bytes(archive_bytes)

        logger.info(f"Extract archive {s3_file_path}")
        result = subprocess.run(
            [r"C:\Program Files\7-Zip\7z.exe", "x", str(archive_path), f"-o{context.root_folder}", "-y"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"7z extraction failed:\n{result.stdout}\n{result.stderr}")

        logger.info("Extraction done...")

        # list_result = subprocess.run(
        #     [r"C:\Program Files\7-Zip\7z.exe", "l", "-slt", str(archive_path)],
        #     capture_output=True,
        #     text=True,
        # )
        # now = time.time()
        # for line in list_result.stdout.splitlines():
        #     if line.startswith("Path = "):
        #         rel_path = line[len("Path = ") :].strip()
        #         extracted_file = context.root_folder / rel_path
        #         if extracted_file.is_file():
        #             os.utime(extracted_file, (now, now))


def warn_if_source_dirty() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "Engine/Source"],
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        logger.warning(
            "You have uncommitted changes under Engine/Source (or the game project's "
            "Source folder). Synced binaries reflect the last committed state only — "
            "you'll likely need to rebuild before your local changes take effect."
        )


def apply_checkpoint(context: Context, version: str, old_manifest: Manifest) -> Manifest:
    logger.info(f"Apply checkpoint {version} (full state)...")

    download_and_extract_archive(context, f"checkpoints/{version}.7z")

    manifest: VersionManifest = context.s3_client.download_json(context.s3_bucket_name, f"manifests/{version}.json")
    new_manifest = manifest["files"]

    stale = [p for p in old_manifest if p not in new_manifest]
    for rel in stale:
        p = context.root_folder / rel
        if p.exists():
            p.unlink()
    if stale:
        logger.info(f"Removed {len(stale)} stale files")

    logger.info(f"Checkpoint applied: {len(new_manifest)} files total")
    return new_manifest


def apply_delta(context: Context, version: str, local_manifest: Manifest) -> Manifest:
    manifest: VersionManifest = context.s3_client.download_json(context.s3_bucket_name, f"manifests/{version}.json")

    if manifest["changed"]:
        download_and_extract_archive(context, f"deltas/{version}.7z")
        logger.info(f"Applied {len(manifest['changed'])} changed files")

    if manifest["removed"]:
        for rel in manifest["removed"]:
            p = context.root_folder / rel
            if p.exists():
                p.unlink()
            local_manifest.pop(rel, None)

        logger.info(f"Removed {len(manifest['removed'])} stale files")

    return manifest["files"]


def sync(context: Context, target_version: str, state: LocalState) -> LocalState:
    logger.info("=== Start syncing binaries ===")

    target_idx: int = context.commit_index.index(target_version)

    current_version = state.get("version")
    start_idx: int
    if current_version is None:
        start_idx = 0
    else:
        start_idx = context.commit_index.index(current_version) + 1

    try:
        logger.info("Download checkpoints")
        checkpoints = context.s3_client.download_json(context.s3_bucket_name, "checkpoints.json", default=[])
    except ClientError:
        checkpoints = []

    applicable_checkpoints = [v for v in checkpoints if v in context.commit_index and start_idx <= context.commit_index.index(v) <= target_idx]

    manifest: Manifest = state.get("manifest", {})
    resume_idx = start_idx

    if applicable_checkpoints:
        best_checkpoint = max(applicable_checkpoints, key=lambda v: context.commit_index.index(v))
        manifest = apply_checkpoint(context, best_checkpoint, manifest)
        resume_idx = context.commit_index.index(best_checkpoint) + 1
    else:
        logger.info("No checkpoint to apply")

    pending = context.commit_index[resume_idx : target_idx + 1]

    if not pending and not applicable_checkpoints:
        logger.info("No delta to apply")
        return state

    num_delta: int = len(pending)
    logger.info(f"Need to apply {num_delta} deltas")

    for index, version in enumerate(pending, start=1):
        logger.info(f"Apply delta {index} / {num_delta} : {version}")
        manifest = apply_delta(context, version, manifest)

    logger.info(f"=== Finished syncing. Now at {target_version} ===")
    return LocalState(version=target_version, manifest=manifest)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Check and install Unreal Engine installation for the given project.")
    parser.add_argument("--uproject-path", type=Path, help=("Path to a native uproject file"))
    parser.add_argument("--s3-bucket-name", type=str, help=("AWS S3 Bucket Name"))
    parser.add_argument("--s3-bucket-region", type=str, help=("AWS S3 Bucket Region"))
    parser.add_argument("--s3-access-key", type=str, help=("AWS S3 Access Key"))
    parser.add_argument("--s3-secret-key", type=str, help=("AWS S3 Secret Key"))

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

    local_state = LocalStateManager()

    context = Context(engine.root_path, args)

    warn_if_source_dirty()

    ancestry = get_local_ancestry(engine.root_path)
    target_version, is_exact_match = resolve_nearest_published_ancestor(context.commit_index, ancestry)

    if target_version is None:
        logger.info("No published version found in HEAD's ancestry — nothing to sync.")
        return

    current_version = local_state.data.get("version")

    if current_version:
        if current_version not in context.commit_index:
            raise RuntimeError(
                f"Local version {current_version} not found in remote index — "
                f"history may have been pruned. Delete {LOCAL_STATE_FILE} to force a full resync."
            )

        if current_version == target_version:
            logger.info(f"Already up to date ({target_version})")
            return

    logger.info(f"Will sync up to {target_version}")

    if not is_exact_match:
        logger.warning(
            f"No commit in HEAD's ancestry matches a published version — this usually means "
            f"history was rewritten on the published branch (a force-push). Falling back to "
            f"the latest published version ({target_version[:8]}), which may not exactly "
            f"match your current source. You may need a local rebuild."
        )

    local_state.data = sync(context, target_version, local_state.data)
    local_state.save()


if __name__ == "__main__":
    main()
