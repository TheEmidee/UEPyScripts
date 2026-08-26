"""
Publishes engine + game binaries as a single unified stream:
  - DLL/EXE/LIB/.modules/.target files (plus any configured glob patterns)
    go through one delta+checkpoint pipeline in S3, with paths relative to
    the common root shared by the engine and project folders
  - PDB/DLL/EXE files are additionally indexed into a Windows symbol store via symstore.exe
  - PDBs are NOT included in the delta/checkpoint pipeline (symbol store only)
  - Version resolution is keyed by git commit SHA (no git push required)
  - Old versions beyond the retention window are pruned automatically
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

import blake3
from gamedevtools.s3 import S3Client

from uepyscripts import logger
from uepyscripts.internal.engine import resolve_engine
from uepyscripts.internal.project import resolve_project
from uepyscripts.tools.ugs.ugs_types import VersionManifest

# ---- CONFIG ----------------------------------------------------------
LOCAL_HASH_CACHE = ".hash-cache.json"

# Extensions that go through the delta/checkpoint sync pipeline (no PDBs — see symstore below)
SYNC_EXT = {".dll", ".exe", ".lib", ".modules", ".target"}

# Extensions indexed into the symbol store (PDBs are the whole point, DLL/EXE ride along
# so minidump/remote-debug analysis can resolve both code and symbols from one place)
SYMSTORE_EXT = {".pdb", ".dll", ".exe"}

IGNORED_FOLDERS = {"Intermediate"}

IGNORED_FILE_PATTERNS = [
    # Matches `.patch_` followed by 1 or more digits at the end of the stem
    re.compile(r"\.patch_\d+$")
]


@dataclass
class FilesConfiguration:
    root_folder: Path  # common ancestor of engine and project folders
    directories: list[str]  # relative to root_folder, covers both engine and game dirs
    glob_files: list[str]  # glob patterns relative to root_folder, e.g. "Engine/Intermediate/Build/BuildRules/*.json"
    checkpoint_interval: int
    keep_checkpoints: int
    symstore_product: str


@dataclass
class HashCacheInfos:
    fingerprint: str
    hash: str


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
        self.local_hash_cache.write_text(json.dumps(serializable, indent=2, sort_keys=True))

    def get(self, path: str) -> HashCacheInfos | None:
        return self.cache.get(path)

    def set(self, path: str, infos: HashCacheInfos) -> None:
        self.cache[path] = infos


class Context:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.s3_client: S3Client = S3Client(
            access_key=args.s3_access_key,
            secret_key=args.s3_secret_key,
            region=args.s3_bucket_region,
        )
        self.symbol_store_path: str = args.symbol_store_path
        self.tmp_root: Path = Path(tempfile.mkdtemp(prefix="publish-"))
        self.hash_cache = HashCache()
        self.current_sha = get_current_sha()

    def finalize(self) -> None:
        if not self.args.keep_temp_directory:
            shutil.rmtree(self.tmp_root, ignore_errors=True)


def get_current_sha() -> str:
    sha = os.environ.get("GIT_COMMIT")  # Jenkins sets this automatically
    if sha:
        return sha
    return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def compute_common_root(engine_root: Path, project_root: Path) -> Path:
    """Finds the common ancestor of the engine and project folders, so every
    file — whether from Engine/ or the game project — can be addressed by a
    single relative path, and zip/extract share one consistent base."""
    common = os.path.commonpath([str(engine_root.resolve()), str(project_root.resolve())])
    return Path(common)


def relative_dirs(base: Path, root: Path, subdirs: list[str]) -> list[str]:
    """Turns a list of dirs relative to `base` into paths relative to `root`."""
    return [(base / d).resolve().relative_to(root).as_posix() for d in subdirs]


def hash_file(path: Path) -> str:
    # multithreaded=True lets blake3 use multiple threads internally for
    # large inputs (small files fall back to single-threaded automatically,
    # so this is safe to always pass)
    return blake3.blake3(max_threads=blake3.blake3.AUTO).update_mmap(str(path)).hexdigest()


def hash_with_cache(f: Path, rel: str, hash_cache: HashCache) -> str:
    """Shared cache-or-hash logic used by both extension-based and
    glob-based scanning, so both stay consistent and avoid re-reading
    files whose mtime+size haven't changed."""
    stat = f.stat()
    fingerprint = f"{stat.st_mtime_ns}:{stat.st_size}"

    cached = hash_cache.get(rel)
    if cached and cached.fingerprint == fingerprint:
        return cached.hash

    file_hash = hash_file(f)
    hash_cache.set(rel, HashCacheInfos(fingerprint, file_hash))
    return file_hash


def has_glob_chars(pattern: str) -> bool:
    return any(ch in pattern for ch in "*?[")


def expand_directories(root: Path, patterns: list[str]) -> list[Path]:
    """Expands cfg.directories entries into actual directories to scan.
    Plain paths (no wildcard characters) are treated as literal directories,
    same as before. Patterns containing wildcards — including a trailing
    '**' for 'this directory and every subdirectory, recursively' — are
    resolved via Path.glob, which natively understands '**' as a recursive
    directory match."""
    dirs: list[Path] = []
    seen: set[Path] = set()

    for pattern in patterns:
        if has_glob_chars(pattern):
            for match in root.glob(pattern):
                if match.is_dir() and match not in seen:
                    seen.add(match)
                    dirs.append(match)
        else:
            d = root / pattern
            if d.exists() and d not in seen:
                seen.add(d)
                dirs.append(d)

    return dirs


def scan_by_ext(cfg: FilesConfiguration, extensions: set[str], hash_cache: HashCache) -> dict[str, str]:
    """Returns {relative_path: sha256}, paths relative to cfg.root_folder.
    cfg.directories entries may be literal paths or glob patterns (including
    a trailing '**' for recursive matching); each matched directory is then
    walked for files matching `extensions`. Reuses cached hashes when
    mtime+size haven't changed, so unchanged files (the vast majority on
    any given run) are never re-read."""
    state: dict[str, str] = {}
    repo_root = cfg.root_folder

    for base in expand_directories(repo_root, cfg.directories):
        for root, dirs, files in os.walk(base):
            dirs[:] = [d_name for d_name in dirs if d_name not in IGNORED_FOLDERS]

            root_path = Path(root)

            for file_name in files:
                f = root_path / file_name

                if f.suffix.lower() not in extensions:
                    continue

                if any(pattern.search(f.stem) for pattern in IGNORED_FILE_PATTERNS):
                    continue

                rel = f.relative_to(repo_root).as_posix()
                state[rel] = hash_with_cache(f, rel, hash_cache)

    return state


def scan_by_glob(cfg: FilesConfiguration, hash_cache: HashCache) -> dict[str, str]:
    """Returns {relative_path: sha256} for every file matching cfg.glob_files
    (patterns relative to cfg.root_folder). Supports '**' for recursive
    matching, e.g. 'Engine/Intermediate/Build/Win64/x64/**/*.generated.h'
    matches that file anywhere under x64/, at any depth. Unlike scan_by_ext,
    this is not filtered by IGNORED_FOLDERS — if a pattern matches a file,
    it's included, since an explicit glob is an explicit request."""
    state: dict[str, str] = {}
    repo_root = cfg.root_folder

    for pattern in cfg.glob_files:
        for f in repo_root.glob(pattern):
            if not f.is_file():
                continue

            if any(p.search(f.stem) for p in IGNORED_FILE_PATTERNS):
                continue

            rel = f.relative_to(repo_root).as_posix()
            state[rel] = hash_with_cache(f, rel, hash_cache)

    return state


def scan_sync_files(cfg: FilesConfiguration, hash_cache: HashCache) -> dict[str, str]:
    """Combined scan for the delta/checkpoint pipeline: extension-matched
    files under cfg.directories, plus anything matched by cfg.glob_files."""
    state = scan_by_ext(cfg, SYNC_EXT, hash_cache)
    state.update(scan_by_glob(cfg, hash_cache))
    return state


def compute_diff(old: dict[str, str], new: dict[str, str]) -> tuple[list[str], list[str]]:
    changed = [p for p, h in new.items() if old.get(p) != h]
    removed = [p for p in old if p not in new]
    return changed, removed


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


def build_zip(files_root_dir: Path, paths: list[str], output_dir: Path) -> Path:
    """Builds a .7z archive containing the given relative paths (relative to
    files_root_dir — the common root — preserving whether they came from
    Engine/ or the game project). Returns the path to the archive on disk
    (caller is responsible for cleaning it up)."""
    archive_path = output_dir / f"{uuid.uuid4().hex}.7z"
    logger.info(f"Destination : {archive_path}")

    list_file = output_dir / f"{uuid.uuid4().hex}-files.txt"
    list_file.write_text("\n".join(paths), encoding="utf-8")

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


def prune_old_versions(context: Context, cfg: FilesConfiguration, index: list[str], checkpoints: list[str]) -> tuple[list[str], list[str]]:
    cfg_keep = cfg.keep_checkpoints
    logger.info(f"Try to prune old versions. Current number of checkpoints: {len(checkpoints)}. Keep: {cfg_keep}")

    if len(checkpoints) <= cfg_keep:
        logger.info("There are not enough checkpoints to do anything")
        return index, checkpoints

    checkpoints_to_keep = checkpoints[-cfg_keep:]
    checkpoints_to_delete = checkpoints[:-cfg_keep]
    oldest_kept_version = checkpoints_to_keep[0]
    cutoff_idx = index.index(oldest_kept_version)
    versions_to_delete = index[:cutoff_idx]

    if not versions_to_delete:
        logger.info("No versions to delete")
        return index, checkpoints_to_keep

    keys_to_delete = []
    for v in versions_to_delete:
        keys_to_delete.append(f"manifests/{v}.json")
        keys_to_delete.append(f"deltas/{v}.7z")
    for v in checkpoints_to_delete:
        keys_to_delete.append(f"checkpoints/{v}.7z")

    logger.info(f"Pruning {len(versions_to_delete)} version(s), {len(checkpoints_to_delete)} checkpoint(s)")
    context.s3_client.delete_keys(context.args.s3_bucket_name, keys_to_delete)

    return index[cutoff_idx:], checkpoints_to_keep


def publish_to_symbol_store(context: Context, paths: list[str], cfg: FilesConfiguration) -> None:
    """Indexes PDB/DLL/EXE files into the symbol store via symstore.exe."""
    logger.info("Publish to symbol store")

    if not paths:
        logger.info("Nothing to upload.")
        return

    logger.info(f"Indexing {len(paths)} file(s) into symbol store...")

    root = cfg.root_folder

    list_file = context.tmp_root / f"{uuid.uuid4().hex}-symstore-files.txt"
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


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Check and install Unreal Engine installation for the given project.")
    parser.add_argument("--uproject-path", type=Path, help=("Path to a native uproject file"))
    parser.add_argument("--skip-upload", action=argparse.BooleanOptionalAction, help=("Set this to not upload anything on S3"))
    parser.add_argument(
        "--keep-temp-directory",
        action=argparse.BooleanOptionalAction,
        help=("Set this to not delete the temporary directory when the script finishes"),
    )
    parser.add_argument("--s3-bucket-name", type=str, help=("AWS S3 Bucket Name"))
    parser.add_argument("--s3-bucket-region", type=str, help=("AWS S3 Bucket Region"))
    parser.add_argument("--s3-access-key", type=str, help=("AWS S3 Access Key"))
    parser.add_argument("--s3-secret-key", type=str, help=("AWS S3 Secret Key"))
    parser.add_argument("--disable-symbol-store-upload", action=argparse.BooleanOptionalAction)
    parser.add_argument("--symbol-store-path", type=str, help=("Path of the shared symbol store folder"))
    parser.add_argument(
        "--checkpoint_interval",
        type=int,
        default=20,
        help="Publish a full checkpoint every N versions (default: 20)",
    )
    parser.add_argument(
        "--keep_checkpoints",
        type=int,
        default=2,
        help="Number of checkpoints to retain; older ones (and their deltas) get pruned (default: 2)",
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

    cfg = FilesConfiguration(
        root_folder=engine.root_path,
        directories=["Engine/Binaries/Win64", "Engine/Platforms", "Engine/Plugins", "Engine/Intermediate/Build/BuildRules", "Engine/Intermediate/Build/Win64/**/"],
        glob_files=["Engine/Intermediate/Build/BuildRules/*.json", "Engine/Intermediate/Build/Win64/**/*.h"],
        checkpoint_interval=args.checkpoint_interval,
        keep_checkpoints=args.keep_checkpoints,
        symstore_product=project.project_name,
    )

    context = Context(args)

    try:
        logger.info("=== Publish binary files ===")

        logger.info("Download index.json")
        index = context.s3_client.download_json(context.args.s3_bucket_name, "index.json", default=[])

        if len(index) == 0:
            logger.info("Empty index.json. Fresh sync")
        elif context.current_sha in index:
            logger.info(f"{context.current_sha} already published, skipping (likely a CI re-run of an already-built commit)")
            logger.info("=== Finished processing binary files ===")
            return

        logger.info("Scan file states")
        new_state = scan_sync_files(cfg, context.hash_cache)
        logger.info(f"Finished scan. Found {len(new_state)} files.")

        logger.info("Download JSON with old state")
        old_state = context.s3_client.download_json(context.args.s3_bucket_name, f"manifests/{index[-1]}.json")["files"] if index else {}

        changed, removed = compute_diff(old_state, new_state)
        version = None
        if changed or removed:
            version = context.current_sha
            logger.info(f"Publishing {version}: {len(changed)} changed, {len(removed)} removed")

            if changed:
                logger.info("Saving list of changed files in Engine/Saved/changed_files.txt")
                with open(engine.saved_path.joinpath("changed_files.txt").resolve(), "w") as file:
                    file.write("\n".join(changed))

                logger.info("Build zip of changed files")
                zip_file_path = build_zip(cfg.root_folder, changed, context.tmp_root)

                if context.args.skip_upload:
                    return
                
                logger.info("Upload zip")
                context.s3_client.upload_file(context.args.s3_bucket_name, f"deltas/{version}.7z", zip_file_path)
                zip_file_path.unlink()

            manifest_payload: VersionManifest = {
                "files": new_state,
                "changed": changed,
                "removed": removed,
            }
            context.s3_client.upload_bytes(
                context.args.s3_bucket_name,
                f"manifests/{version}.json",
                json.dumps(manifest_payload).encode(),
                content_type="application/json",
            )

            index.append(version)

            logger.info("Download JSON with checkpoints")
            checkpoints = context.s3_client.download_json(context.args.s3_bucket_name, "checkpoints.json", default=[])

            logger.info(f"Checkpoint interval: {cfg.checkpoint_interval} - Number of deltas : {len(index)}")

            if len(index) % cfg.checkpoint_interval == 0:
                logger.info(f"Need to create a new checkpoint at version #{len(index)}")
                zip_file_path = build_zip(cfg.root_folder, list(new_state.keys()), context.tmp_root)

                logger.info("Upload zip")
                context.s3_client.upload_file(context.args.s3_bucket_name, f"checkpoints/{version}.7z", zip_file_path)
                zip_file_path.unlink()
                checkpoints.append(version)
            else:
                logger.info("No need to create a new checkpoint")

            index, checkpoints = prune_old_versions(context, cfg, index, checkpoints)

            logger.info("Upload index.json")
            context.s3_client.upload_bytes(context.args.s3_bucket_name, "index.json", json.dumps(index).encode(), content_type="application/json")

            logger.info("Upload checkpoints.json")
            context.s3_client.upload_bytes(
                context.args.s3_bucket_name, "checkpoints.json", json.dumps(checkpoints).encode(), content_type="application/json"
            )
        else:
            logger.info("No changes in synced binaries.")

        if not context.args.disable_symbol_store_upload:
            # Symbol store publish (PDB/DLL/EXE), independent of whether the sync pipeline changed.
            # Deliberately NOT combined with glob_files — those are for arbitrary extra files
            # (like the BuildRules JSONs) that have no business being in the symbol store.
            logger.info("Scan file states for debug files")
            symstore_state = scan_by_ext(cfg, SYMSTORE_EXT, context.hash_cache)
            logger.info(f"Finished scan. Found {len(symstore_state)} files.")

            logger.info("Download symstore-manifest.json")
            prev_symstore_state = context.s3_client.download_json(context.args.s3_bucket_name, "symstore-manifest.json", default={})
            symstore_changed, _ = compute_diff(prev_symstore_state, symstore_state)

            if symstore_changed:
                publish_to_symbol_store(context, symstore_changed, cfg)

                logger.info("Upload symstore-manifest.json")
                context.s3_client.upload_bytes(
                    context.args.s3_bucket_name, "symstore-manifest.json", json.dumps(symstore_state).encode(), content_type="application/json"
                )
            else:
                logger.info("No changes for symbol store")
        else:
            logger.info("Upload on the symbol store is disabled")

        logger.info("=== Finished processing binary files ===")

        logger.info("Save hash cache")
        context.hash_cache.save()
    finally:
        context.finalize()


if __name__ == "__main__":
    main()
