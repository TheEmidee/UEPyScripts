"""
Publishes engine/game binaries per category:
  - DLL/EXE/LIB/.modules files go through the delta+checkpoint pipeline in S3
  - PDB/DLL/EXE files are additionally indexed into a Windows symbol store via symstore.exe
  - PDBs are NOT included in the delta/checkpoint pipeline (symbol store only)
  - Version resolution is keyed by git commit SHA (no git push required)
  - Old versions beyond the retention window are pruned automatically
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from typing import TypedDict
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import blake3
from gamedevtools.s3 import S3Client

from uepyscripts import logger
from uepyscripts.internal.engine import resolve_engine
from uepyscripts.internal.project import resolve_project

# ---- CONFIG ----------------------------------------------------------
LOCAL_HASH_CACHE = ".hash-cache.json"

# Extensions that go through the delta/checkpoint sync pipeline (no PDBs — see symstore below)
SYNC_EXT = {".dll", ".exe", ".lib", ".modules"}

# Extensions indexed into the symbol store (PDBs are the whole point, DLL/EXE ride along
# so minidump/remote-debug analysis can resolve both code and symbols from one place)
SYMSTORE_EXT = {".pdb", ".dll", ".exe"}

IGNORED_FOLDERS = {"Intermediate"}

IGNORED_FILE_PATTERNS = [
    # Matches `.patch_` followed by 1 or more digits at the end of the stem
    re.compile(r"\.patch_\d+$")
]


@dataclass
class RetentionConfiguration:
    category: str
    root_folder: Path
    directories: list[str]
    checkpoint_interval: int
    keep_checkpoints: int
    symstore_product: str


@dataclass
class HashCacheInfos:
    fingerprint: str
    hash: str

Manifest = dict[str, str]

class VersionManifest(TypedDict):
    files: Manifest       # full state at this version: {relative_path: sha256}
    changed: list[str]    # files added or modified since the previous version
    removed: list[str]    # files removed since the previous version

class HashCache:
    def __init__(self) -> None:
        self.cache: dict[str, HashCacheInfos] = dict()
        self.local_hash_cache = Path(LOCAL_HASH_CACHE)

        if self.local_hash_cache.exists():
            raw = json.loads(self.local_hash_cache.read_text())
            self.cache = {path: HashCacheInfos(**entry) for path, entry in raw.items()}

    def save(self) -> None:
        self.local_hash_cache.parent.mkdir(parents=True, exist_ok=True)
        serializable = {path: asdict(entry) for path, entry in self.cache.items()}
        self.local_hash_cache.write_text(json.dumps(serializable))

    def get(self, path: str) -> HashCacheInfos:
        return self.cache.get(path)

    def set(self, path: str, infos: HashCacheInfos) -> None:
        self.cache[path] = infos


class Context:
    def __init__(self, args: argparse.Namespace) -> None:
        self.s3_bucket_name: str = args.s3_bucket_name
        self.s3_bucket_region: str = args.s3_bucket_region
        self.s3_client: S3Client = S3Client(
            access_key=args.s3_access_key,
            secret_key=args.s3_secret_key,
            region=args.s3_bucket_region,
        )
        self.upload_pdbs = not args.no_symbol_store_upload
        self.symbol_store_path: str = args.symbol_store_path
        self.tmp_root: Path = Path(tempfile.mkdtemp(prefix="publish-"))
        self.hash_cache = HashCache()
        self.current_sha = get_current_sha()

    def finalize(self) -> None:
        shutil.rmtree(self.tmp_root, ignore_errors=True)


def get_current_sha() -> str:
    sha = os.environ.get("GIT_COMMIT")  # Jenkins sets this automatically
    if sha:
        return sha
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def hash_file(path: Path) -> str:
    # multithreaded=True lets blake3 use multiple threads internally for
    # large inputs (small files fall back to single-threaded automatically,
    # so this is safe to always pass)
    return blake3.blake3(max_threads=blake3.blake3.AUTO).update_mmap(str(path)).hexdigest()


def scan_by_ext(cfg: RetentionConfiguration, extensions: set[str], hash_cache: HashCache) -> dict[str, str]:
    """Returns {relative_path: sha256}. Reuses cached hashes when mtime+size
    haven't changed, so unchanged files (the vast majority on any given run)
    are never re-read."""
    state: dict[str, str] = {}
    repo_root = cfg.root_folder

    for d in cfg.directories:
        base = repo_root / d
        if not base.exists():
            continue

        # os.walk allows modifying 'dirs' in-place to skip traversing ignored folders
        for root, dirs, files in os.walk(base):
            # Prune ignored directory names instantly
            dirs[:] = [d_name for d_name in dirs if d_name not in IGNORED_FOLDERS]

            root_path = Path(root)

            for file_name in files:
                f = root_path / file_name

                if f.suffix.lower() not in extensions:
                    continue

                # Skip file if ANY pattern matches the stem
                if any(pattern.search(f.stem) for pattern in IGNORED_FILE_PATTERNS):
                    continue

                rel = f.relative_to(repo_root).as_posix()
                # Check if relative path parts match any ignored folder path
                rel_parts = set(Path(rel).parts[:-1])
                if rel_parts.intersection(IGNORED_FOLDERS):
                    continue

                stat = f.stat()
                fingerprint = f"{stat.st_mtime_ns}:{stat.st_size}"

                cached = hash_cache.get(rel)
                if cached and cached.fingerprint == fingerprint:
                    state[rel] = cached.hash
                else:
                    file_hash = hash_file(f)
                    state[rel] = file_hash
                    hash_cache.set(rel, HashCacheInfos(fingerprint, file_hash))

    return state


def compute_diff(old: dict[str, str], new: dict[str, str]) -> tuple[list[str], list[str]]:
    changed = [p for p, h in new.items() if old.get(p) != h]
    removed = [p for p in old if p not in new]
    return changed, removed


def build_zip(files_root_dir: Path, paths: list[str], output_dir: Path) -> Path:
    """Builds a .7z archive containing the given relative paths, preserving
    their directory structure. Returns the path to the archive on disk
    (caller is responsible for cleaning it up)."""

    def human_readable_size(num_bytes: int) -> str:
        size = float(num_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def human_readable_duration(seconds: float) -> str:
        if seconds < 60:
            return f"{seconds:.1f}s"
        minutes, secs = divmod(seconds, 60)
        return f"{int(minutes)}m {secs:.0f}s"

    archive_path = output_dir / f"{uuid.uuid4().hex}.7z"
    logger.info(f"Destination : {archive_path}")

    list_file = output_dir / f"{uuid.uuid4().hex}-files.txt"
    # write the list of all the files to zip together
    list_file.write_text("\n".join(paths), encoding="utf-8")
    logger.info(f"Wrote file list at : {list_file}")

    start_time = time.perf_counter()
    logger.info(f"Start zipping {len(paths)} files")

    try:
        result = subprocess.run(
            [r"C:\Program Files\7-Zip\7z.exe", "a", "-t7z", "-mx=5", str(archive_path), f"@{list_file}"],
            cwd=files_root_dir,  # so relative paths in files.txt resolve correctly
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"7z archive creation failed:\n{result.stdout}\n{result.stderr}")
    finally:
        list_file.unlink(missing_ok=True)

    elapsed = time.perf_counter() - start_time

    size = archive_path.stat().st_size
    logger.info(f"Built {archive_path.name} ({human_readable_size(size)}) in {human_readable_duration(elapsed)}")

    return archive_path


def prune_old_versions(context: Context, cfg: RetentionConfiguration, index: list[str], checkpoints: list[str]) -> tuple[list[str], list[str]]:
    logger.info(
        f"Try to prune old versions. Current number of checkpoint : {len(checkpoints)}. Number of checkpoint to keep : {cfg.keep_checkpoints}"
    )

    if len(checkpoints) <= cfg.keep_checkpoints:
        logger.info("There are not enough checkpoints to do anything")
        return index, checkpoints

    checkpoints_to_keep = checkpoints[-cfg.keep_checkpoints :]
    checkpoints_to_delete = checkpoints[: -cfg.keep_checkpoints]
    oldest_kept_version = checkpoints_to_keep[0]
    cutoff_idx = index.index(oldest_kept_version)
    versions_to_delete = index[:cutoff_idx]

    if not versions_to_delete:
        logger.info("No versions to delete")
        return index, checkpoints_to_keep

    keys_to_delete = []
    for v in versions_to_delete:
        keys_to_delete.append(f"{cfg.category}/manifests/{v}.json")
        keys_to_delete.append(f"{cfg.category}/deltas/{v}.7z")
    for v in checkpoints_to_delete:
        keys_to_delete.append(f"{cfg.category}/checkpoints/{v}.7z")

    logger.info(f"Pruning {len(versions_to_delete)} version(s), {len(checkpoints_to_delete)} checkpoint(s)")
    context.s3_client.delete_keys(context.s3_bucket_name, keys_to_delete)

    return index[cutoff_idx:], checkpoints_to_keep


def publish_to_symbol_store(context: Context, paths: list[str], cfg: RetentionConfiguration) -> None:
    """Indexes PDB/DLL/EXE files into the symbol store via symstore.exe."""
    logger.info("Publish to symbol store")

    if not paths:
        logger.info("Nothing to upload.")
        return

    logger.info(f"Indexing {len(paths)} file(s) into symbol store...")

    root = cfg.root_folder

    list_file = context.tmp_root / f"{uuid.uuid4().hex}-symstore-files.txt"
    # symstore's /f needs absolute paths, one per line
    list_file.write_text(
        "\n".join(str((root / p).resolve()) for p in paths),
        encoding="utf-8",
    )

    try:
        result = subprocess.run(
            [
                r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\symstore.exe",
                "add",
                "/f",
                f"@{list_file}",
                "/s",
                context.symbol_store_path,
                "/t",
                cfg.symstore_product,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"symstore add failed:\n{result.stdout}\n{result.stderr}")
    finally:
        list_file.unlink(missing_ok=True)

    logger.info(f"Symbol store updated for {cfg.symstore_product}")


def publish_category(context: Context, cfg: RetentionConfiguration) -> str | None:
    """Publishes one category's binaries. Returns the new version string, or the
    last-published version if nothing changed (so the commit index still gets an entry)."""

    logger.info(f"=== Publish binary files for {cfg.category} ===")

    logger.info("Download index.json")
    index = context.s3_client.download_json(context.s3_bucket_name, f"{cfg.category}/index.json", default=[])

    if context.current_sha in index:
        print(f"  {context} already published for this category, skipping "
              f"(likely a CI re-run of an already-built commit)")
        return context.current_sha

    logger.info("Scan file states")
    new_state = scan_by_ext(cfg, SYNC_EXT, context.hash_cache)
    logger.info(f"Finished scan. Found {len(new_state)} files.")

    logger.info("Download JSON with old state")
    old_state = (
        context.s3_client.download_json(context.s3_bucket_name, f"{cfg.category}/manifests/{index[-1]}.json") 
        if index else {}
    )

    changed, removed = compute_diff(old_state, new_state)
    version = None
    if changed or removed:
        version = context.current_sha
        logger.info(f"Publishing {version}: {len(changed)} changed, {len(removed)} removed")

        if changed:
            logger.info("Build zip of changed files")
            zip_file_path = build_zip(cfg.root_folder, changed, context.tmp_root)

            logger.info("Upload zip")
            context.s3_client.upload_file(context.s3_bucket_name, f"{cfg.category}/deltas/{version}.7z", zip_file_path)
            zip_file_path.unlink()

        manifest_payload: VersionManifest = {
            "files": new_state,
            "changed": changed,
            "removed": removed,
        }
        context.s3_client.upload_bytes(
            context.s3_bucket_name, 
            f"{cfg.category}/manifests/{version}.json",
            json.dumps(manifest_payload).encode(), content_type="application/json",
        )

        index.append(version)

        logger.info("Download JSON with checkpoints")
        checkpoints = context.s3_client.download_json(context.s3_bucket_name, f"{cfg.category}/checkpoints.json", default=[])

        logger.info(f"Checkpoint interval: {cfg.checkpoint_interval} - Number of deltas : {len(index)}")

        if len(index) % cfg.checkpoint_interval == 0:
            logger.info(f"Need to create a new checkpoint at version #{len(index)}")
            logger.info("Build zip for the checkpoint")
            zip_file_path = build_zip(cfg.root_folder, list(new_state.keys()), context.tmp_root)

            logger.info("Upload zip")
            context.s3_client.upload_file(context.s3_bucket_name, f"{cfg.category}/checkpoints/{version}.7z", zip_file_path)
            zip_file_path.unlink()
            checkpoints.append(version)
        else:
            logger.info("No need to create a new checkpoint")

        index, checkpoints = prune_old_versions(context, cfg, index, checkpoints)

        logger.info("Upload index.json")
        context.s3_client.upload_bytes(
            context.s3_bucket_name, f"{cfg.category}/index.json", json.dumps(index).encode(), content_type="application/json"
        )

        logger.info("Upload checkpoints.json")
        context.s3_client.upload_bytes(
            context.s3_bucket_name, f"{cfg.category}/checkpoints.json", json.dumps(checkpoints).encode(), content_type="application/json"
        )
    else:
        logger.info("No changes in synced binaries.")

    # 2. Symbol store publish (PDB/DLL/EXE), independent of whether the sync pipeline changed —
    #    diffed separately since PDBs aren't tracked in new_state above.
    logger.info("Scan file states for debug files")
    symstore_state = scan_by_ext(cfg, SYMSTORE_EXT, context.hash_cache)
    logger.info(f"Finished scan. Found {len(symstore_state)} files.")

    logger.info("Download symstore-manifest.json")
    prev_symstore_state = context.s3_client.download_json(context.s3_bucket_name, f"{cfg.category}/symstore-manifest.json", default={})
    symstore_changed, _ = compute_diff(prev_symstore_state, symstore_state)

    if symstore_changed and context.upload_pdbs:
        publish_to_symbol_store(context, symstore_changed, cfg)

        logger.info("Upload symstore-manifest.json")
        context.s3_client.upload_bytes(
            context.s3_bucket_name, f"{cfg.category}/symstore-manifest.json", json.dumps(symstore_state).encode(), content_type="application/json"
        )
    else:
        logger.info("No changes for symbol store")

    logger.info(f"=== Finished processing binary files for {cfg.category} ===")

    return version or (index[-1] if index else None)


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
    parser.add_argument(
        '--no_symbol_store_upload', 
        action=argparse.BooleanOptionalAction
    )
    parser.add_argument(
        "--symbol_store_path",
        type=str,
        help=("Path of the shared symbol store folder"),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_arguments()

    logger.info("Publish binaries...")

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

    try:
        versions = {
            "engine": publish_category(
                context,
                RetentionConfiguration(
                    "engine", engine.root_path, ["Engine/Binaries/Win64", "Engine/Plugins"], 30, 2, f"{project.project_name}-Engine"
                ),
            ),
            "game": publish_category(
                context, RetentionConfiguration("game", project.root_folder, ["Binaries/Win64", "Plugins"], 10, 3, f"{project.project_name}-Game")
            ),
        }

        logger.info("Save hash cache")
        context.hash_cache.save()
    finally:
        context.finalize()


if __name__ == "__main__":
    main()
