import argparse
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict

from botocore.exceptions import ClientError  # type: ignore[import-untyped]
from gamedevtools.s3 import S3Client

from uepyscripts import logger
from uepyscripts.internal.engine import resolve_engine
from uepyscripts.internal.project import resolve_project

"""
Syncs local engine/game binaries to match the current git HEAD (or nearest
published ancestor commit), per category (engine / game).

For each category:
  - Resolves the target binary version from commits-index.json, walking
    HEAD's ancestry until a commit with a published version is found.
  - Jumps to the newest applicable checkpoint (full state) if one exists
    between the client's current version and the target, then replays any
    remaining deltas on top.
  - PDB files are never downloaded here — they're excluded from the
    delta/checkpoint pipeline entirely and served on-demand via the
    symbol store instead. Configure your debugger's symbol path separately.

Requires 7z.exe on PATH (or set SEVEN_ZIP_PATH below).
"""

# ---- CONFIG ----------------------------------------------------------
LOCAL_STATE_FILE = ".sync-state.json"  # {"engine": {"version": ..., "manifest": {...}}, "game": {...}}
ANCESTRY_LOOKBACK = 2000  # max commits to walk back looking for a published version


@dataclass
class DeltaInfo(TypedDict):
    changed: list[str]
    removed: list[str]


@dataclass
class CategoryState(TypedDict):
    version: str | None
    manifest: dict[str, str]


# Manifest: {relative_path: sha256}
Manifest = dict[str, str]

# {category: version} resolved for a given commit
CategoryVersions = dict[str, str]

# One entry in commits-index.json: {"sha": ..., "engine": ..., "game": ..., ...}
CommitEntry = dict[str, str]

class VersionManifest(TypedDict):
    files: Manifest       # full state at this version: {relative_path: sha256}
    changed: list[str]    # files added or modified since the previous version
    removed: list[str]    # files removed since the previous version

@dataclass
class CategoryInfo:
    name: str
    root_folder: Path


class Context:
    def __init__(self, args: argparse.Namespace) -> None:
        self.s3_bucket_name: str = args.s3_bucket_name
        self.s3_bucket_region: str = args.s3_bucket_region
        self.s3_client: S3Client = S3Client(
            access_key=args.s3_access_key,
            secret_key=args.s3_secret_key,
            region=args.s3_bucket_region,
        )


class LocalState:
    def __init__(self) -> None:
        self.path = Path(LOCAL_STATE_FILE)
        self.data: dict[str, CategoryState] = {}

        if self.path.exists():
            self.data = json.loads(self.path.read_text())

    def get(self, category: str) -> CategoryState:
        return self.data.get(category, CategoryState(version=None, manifest={}))

    def set(self, category: str, state: CategoryState) -> None:
        self.data[category] = state

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2))


def get_local_ancestry(limit: int = ANCESTRY_LOOKBACK) -> list[str]:
    out = subprocess.check_output(["git", "log", f"-{limit}", "--format=%H", "HEAD"], text=True)
    return out.splitlines()


def extract_archive_bytes(data: bytes, output_folder: Path) -> None:
    """Extracts a .7z archive (as raw bytes) into the current directory."""
    if not data:
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        archive_path = Path(tmpdir) / "archive.7z"
        archive_path.write_bytes(data)

        result = subprocess.run(
            [r"C:\Program Files\7-Zip\7z.exe", "x", str(archive_path), f"-o{output_folder}", "-y"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"7z extraction failed:\n{result.stdout}\n{result.stderr}")


def warn_if_source_dirty() -> None:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--", "Engine/Source", "MyGame/Source"],
        capture_output=True,
        text=True,
    )
    if result.stdout.strip():
        logger.warning(
            "You have uncommitted changes under Engine/Source or MyGame/Source. "
            "Synced binaries reflect the last committed state only — you'll likely need "
            "to rebuild before your local changes take effect."
        )


def apply_checkpoint(context: Context, category_info: CategoryInfo, version: str, old_manifest: Manifest) -> Manifest:
    logger.info(f"Jumping to checkpoint {version} (full state)...")
    archive_bytes = context.s3_client.download_bytes(context.s3_bucket_name, f"{category_info.name}/checkpoints/{version}.7z")
    extract_archive_bytes(archive_bytes, category_info.root_folder)

    manifest = context.s3_client.download_json(context.s3_bucket_name, f"{category_info.name}/manifests/{version}.json")
    new_manifest = manifest["files"]

    stale = [p for p in old_manifest if p not in new_manifest]
    for rel in stale:
        p = Path(rel)
        if p.exists():
            p.unlink()
    if stale:
        logger.info(f"Removed {len(stale)} stale files")

    logger.info(f"Checkpoint applied: {len(new_manifest)} files total")
    return new_manifest


def apply_delta(context: Context, category_info: CategoryInfo, version: str, local_manifest: Manifest) -> Manifest:
    manifest = context.s3_client.download_json(context.s3_bucket_name, f"{category_info.name}/manifests/{version}.json")

    if manifest["changed"]:
        archive_bytes = context.s3_client.download_bytes(context.s3_bucket_name, f"{category_info.name}/deltas/{version}.7z")

        extract_archive_bytes(archive_bytes, category_info.root_folder)
        logger.info(f"Applied {len(manifest['changed'])} changed files")

    if manifest["removed"]:
        for rel in manifest["removed"]:
            p = Path(rel)
            if p.exists():
                p.unlink()
            local_manifest.pop(rel, None)

        logger.info(f"Removed {len(manifest['removed'])} stale files")

    return manifest["files"]


def sync_category(context: Context, category_info: CategoryInfo, target_version: str, cat_state: CategoryState) -> CategoryState:
    logger.info(f"=== Start syncing for category {category_info.name} ===")
    if cat_state.get("version") == target_version:
        logger.info(f"Already up to date ({target_version})")
        return cat_state

    index = context.s3_client.download_json(context.s3_bucket_name, f"{category_info.name}/index.json")
    try:
        checkpoints = context.s3_client.download_json(context.s3_bucket_name, f"{category_info.name}/checkpoints.json")
    except ClientError:
        checkpoints = []

    if target_version not in index:
        raise RuntimeError(f"[{category_info.name}] target version {target_version} not found in remote index.")
    target_idx = index.index(target_version)

    current_version = cat_state.get("version")
    start_idx: int
    if current_version is None:
        start_idx = 0
    else:
        if current_version not in index:
            raise RuntimeError(
                f"[{category_info.name}] local version {current_version} not found in remote index — "
                f"history may have been pruned. Delete the '{category_info.name}' entry in "
                f"{LOCAL_STATE_FILE} to force a full resync."
            )
        start_idx = index.index(current_version) + 1

    applicable_checkpoints = [v for v in checkpoints if v in index and start_idx <= index.index(v) <= target_idx]

    manifest: Manifest = cat_state.get("manifest", {})
    resume_idx = start_idx

    if applicable_checkpoints:
        best_checkpoint = max(applicable_checkpoints, key=lambda v: index.index(v))
        manifest = apply_checkpoint(context, category_info, best_checkpoint, manifest)
        resume_idx = index.index(best_checkpoint) + 1

    pending = index[resume_idx : target_idx + 1]

    if not pending and not applicable_checkpoints:
        logger.info("Nothing to apply")
        return cat_state

    for version in pending:
        logger.info(f"Syncing {version}...")
        manifest = apply_delta(context, category_info, version, manifest)

    logger.info(f"=== Finished syncing {category_info.name}. Now at {target_version} ===")
    return CategoryState(version=target_version, manifest=manifest)


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Check and install Unreal Engine installation for the given project.")
    parser.add_argument(
        "--uproject_path",
        type=Path,
        help=("Path to a native uproject file"),
    )
    parser.add_argument(
        "--s3_bucket_name",
        type=str,
        help=("AWS S3 Bucket Name"),
    )
    parser.add_argument(
        "--s3_bucket_region",
        type=str,
        help=("AWS S3 Bucket Region"),
    )
    parser.add_argument(
        "--s3_access_key",
        type=str,
        help=("AWS S3 Access Key"),
    )
    parser.add_argument(
        "--s3_secret_key",
        type=str,
        help=("AWS S3 Secret Key"),
    )

    return parser.parse_args()


def resolve_target_versions(context: Context) -> dict[str, str]:
    """Returns {category: version} for the nearest ancestor commit (including
    HEAD itself) that has a published entry in commits-index.json."""
    commit_index_raw = context.s3_client.download_json(context.s3_bucket_name, COMMIT_INDEX_KEY, default=[])
    assert isinstance(commit_index_raw, list)
    commit_index: list[CommitEntry] = commit_index_raw
    index_by_sha: dict[str, CommitEntry] = {entry["sha"]: entry for entry in commit_index}

    ancestry = get_local_ancestry()
    for sha in ancestry:
        if sha in index_by_sha:
            entry = index_by_sha[sha]
            versions: CategoryVersions = {k: v for k, v in entry.items() if k != "sha"}
            logger.info(f"Resolved HEAD ({ancestry[0][:8]}) -> commit {sha[:8]} -> {versions}")
            return versions

    raise RuntimeError(
        "No published binary state found for HEAD or any recent ancestor. "
        "Either this branch has never been built, or it's older than the lookback window."
    )


def main() -> None:
    args = parse_arguments()

    logger.info("Syncing binaries...")

    try:
        project = resolve_project(args.uproject_path)
    except Exception as e:
        logger.fatal(f"Project resolution failed: {e}")
        exit(1)

    if not project.is_native_project:
        logger.fatal("You can only publish binaries for native projects")
        exit(1)

    engine = resolve_engine(project)

    context = Context(args)

    warn_if_source_dirty()

    pins = resolve_target_versions(context)
    local_state = LocalState()

    for category, target_version in pins.items():
        category_state = local_state.get(category)
        category_info = CategoryInfo(category, engine.root_path if category == "engine" else project.root_folder)
        local_state.set(category, sync_category(context, category_info, target_version, category_state))

    local_state.save()


if __name__ == "__main__":
    main()
