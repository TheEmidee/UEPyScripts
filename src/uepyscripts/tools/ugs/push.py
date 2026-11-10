"""
Publishes engine + game binaries to the Publish store (see publish_store.py):
  - DLL/EXE/LIB/.modules/.target files (plus any configured glob patterns) are
    hashed, every file content the bucket doesn't have yet is uploaded as a
    Blob, then the Manifest of the current commit is written
  - PDB/DLL/EXE files are additionally indexed into a Windows symbol store via symstore.exe
  - PDBs are never uploaded as Blobs (symbol store only)
  - Versions are keyed by git commit SHA (no git push required)
  - Retention is handled by ugs.cleanup, never here
"""

import argparse
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import cast

import blake3

from uepyscripts import logger
from uepyscripts.internal.engine import resolve_engine
from uepyscripts.internal.project import resolve_project
from uepyscripts.tools.ugs.git_utils import (
    ANCESTRY_LOOKBACK,
    get_current_branch,
    get_current_sha,
    get_local_ancestry,
)
from uepyscripts.tools.ugs.publish_store import DEFAULT_JOBS, PublishStore
from uepyscripts.tools.ugs.s3_settings import S3_CONFIG_SECTION, add_s3_arguments, resolve_s3_settings
from uepyscripts.tools.ugs.ugs_types import HashCacheEntry, HashCacheManifest, Manifest

# ---- CONFIG ----------------------------------------------------------

# Extensions published as Blobs (no PDBs — see symstore below)
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
    root_folder: Path  # every published path is relative to this folder
    directories: list[str]  # relative to root_folder, covers both engine and game dirs
    glob_files: list[str]  # glob patterns relative to root_folder, e.g. "Engine/Intermediate/Build/BuildRules/*.json"
    symstore_product: str


@dataclass
class HashCacheInfos:
    fingerprint: str
    hash: str


class HashCache:
    def __init__(self, commit_sha: str) -> None:
        self.commit_sha = commit_sha
        self.cache: dict[str, HashCacheInfos] = dict()

    def seed_from(self, files: dict[str, HashCacheEntry]) -> None:
        self.cache = {path: HashCacheInfos(**entry) for path, entry in files.items()}

    def to_manifest(self) -> HashCacheManifest:
        return {
            "commit_sha": self.commit_sha,
            "files": {path: cast(HashCacheEntry, asdict(entry)) for path, entry in self.cache.items()},
        }

    def get(self, path: str) -> HashCacheInfos | None:
        return self.cache.get(path)

    def set(self, path: str, infos: HashCacheInfos) -> None:
        self.cache[path] = infos


class Context:
    def __init__(self, args: argparse.Namespace, root_path: Path, store: PublishStore) -> None:
        self.args = args
        self.store = store
        self.symbol_store_path: str = args.symbol_store_path
        self.tmp_root: Path = Path(tempfile.mkdtemp(prefix="publish-"))
        self.root_path = root_path
        self.current_sha = get_current_sha(root_path)
        self.current_branch = get_current_branch(root_path)
        self.ancestry: list[str] = get_local_ancestry(root_path)
        self.hash_cache = self._load_hash_cache()

    def _load_hash_cache(self) -> HashCache:
        hash_cache = HashCache(self.current_sha)
        manifest = self.store.latest_hash_cache(self.ancestry)
        if manifest is None:
            logger.info("No hash cache found — starting with a cold hash cache")
            return hash_cache

        hash_cache.seed_from(manifest["files"])
        logger.info(f"Seeded hash cache from {manifest['commit_sha']} ({len(manifest['files'])} entries)")
        return hash_cache

    def finalize(self) -> None:
        if not self.args.keep_temp_directory:
            shutil.rmtree(self.tmp_root, ignore_errors=True)


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
    """Returns {relative_path: blake3}, paths relative to cfg.root_folder.
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
    """Returns {relative_path: blake3} for every file matching cfg.glob_files
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
    """Combined scan of every published file: extension-matched
    files under cfg.directories, plus anything matched by cfg.glob_files."""
    state = scan_by_ext(cfg, SYNC_EXT, hash_cache)
    state.update(scan_by_glob(cfg, hash_cache))
    return state


def compute_diff(old: dict[str, str], new: dict[str, str]) -> tuple[list[str], list[str]]:
    changed = [p for p, h in new.items() if old.get(p) != h]
    removed = [p for p in old if p not in new]
    return changed, removed


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
    parser = argparse.ArgumentParser(
        description=(
            "Publish the engine + game binaries for the current git HEAD. "
            f"The S3 info is read from the [{S3_CONFIG_SECTION}] section of Config/PyScripts/config.ini, "
            "and each value can be overridden by its command line argument."
        )
    )
    parser.add_argument("--uproject-path", type=Path, help=("Path to a native uproject file"))
    parser.add_argument(
        "--skip-upload",
        action=argparse.BooleanOptionalAction,
        help=("Scan and write Engine/Saved/changed_files.txt, but don't upload anything or update the symbol store"),
    )
    parser.add_argument(
        "--keep-temp-directory",
        action=argparse.BooleanOptionalAction,
        help=("Set this to not delete the temporary directory when the script finishes"),
    )
    add_s3_arguments(parser)
    parser.add_argument("--disable-symbol-store-upload", action=argparse.BooleanOptionalAction)
    parser.add_argument("--symbol-store-path", type=str, help=("Path of the shared symbol store folder"))
    parser.add_argument(
        "--keep_hash_caches",
        type=int,
        default=100,
        help="Number of hash caches to retain in the bucket; older ones get deleted (default: 100)",
    )
    parser.add_argument("--jobs", type=int, default=DEFAULT_JOBS, help=f"Number of parallel uploads (default: {DEFAULT_JOBS})")

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

    s3_settings = resolve_s3_settings(project, args)
    store = PublishStore.from_settings(s3_settings, jobs=args.jobs)

    cfg = FilesConfiguration(
        root_folder=engine.root_path,
        directories=[
            "Engine/Binaries/Win64",
            "Engine/Plugins",
            "Engine/Platforms",
            "Engine/Intermediate/Build/BuildRules",
            "Engine/Intermediate/Build/Win64/**/",
            "Engine/Plugins/**/Intermediate/**/",
        ],
        glob_files=["Engine/Intermediate/Build/BuildRules/*.json", "Engine/Intermediate/Build/Win64/**/*.h"],
        symstore_product=project.project_name,
    )

    context = Context(args, engine.root_path, store)

    try:
        logger.info("=== Publish binary files ===")
        logger.info(f"Current branch: {context.current_branch}")

        baseline_sha = store.nearest_version(context.ancestry)

        if baseline_sha == context.current_sha:
            logger.info(f"{context.current_sha} already published, skipping (likely a CI re-run of an already-built commit)")
            logger.info("=== Finished processing binary files ===")
            return

        logger.info("Scan file states")
        new_state = scan_sync_files(cfg, context.hash_cache)
        logger.info(f"Finished scan. Found {len(new_state)} files.")

        baseline: Manifest | None = None
        if baseline_sha is None:
            logger.info(f"No published ancestor within the last {ANCESTRY_LOOKBACK} commits — publishing every file")
        else:
            logger.info(f"Using {baseline_sha} as baseline for branch '{context.current_branch}'")
            baseline = store.manifest(baseline_sha)

        changed, removed = compute_diff(baseline or {}, new_state)
        logger.info(f"{len(changed)} changed, {len(removed)} removed since the baseline")

        logger.info("Saving list of changed files in Engine/Saved/changed_files.txt")
        changed_files_path = engine.saved_path.joinpath("changed_files.txt").resolve()
        changed_files_path.parent.mkdir(parents=True, exist_ok=True)
        changed_files_path.write_text("\n".join(changed))

        if context.args.skip_upload:
            logger.info("Skipping the upload (--skip-upload)")
            return

        result = store.publish(context.current_sha, new_state, cfg.root_folder, baseline=baseline)
        logger.info(f"Published {context.current_sha}: {result.uploaded_blobs} new blob(s), {result.reused_blobs} reused")

        if not context.args.disable_symbol_store_upload:
            # Symbol store publish (PDB/DLL/EXE), independent of whether the published files changed.
            # Deliberately NOT combined with glob_files — those are for arbitrary extra files
            # (like the BuildRules JSONs) that have no business being in the symbol store.
            logger.info("Scan file states for debug files")
            symstore_state = scan_by_ext(cfg, SYMSTORE_EXT, context.hash_cache)
            logger.info(f"Finished scan. Found {len(symstore_state)} files.")

            symstore_changed, _ = compute_diff(store.symstore_manifest(), symstore_state)

            if symstore_changed:
                publish_to_symbol_store(context, symstore_changed, cfg)
                store.save_symstore_manifest(symstore_state)
            else:
                logger.info("No changes for symbol store")
        else:
            logger.info("Upload on the symbol store is disabled")

        logger.info("Upload hash cache")
        store.save_hash_cache(context.current_sha, context.hash_cache.to_manifest(), keep=context.args.keep_hash_caches)

        logger.info("=== Finished processing binary files ===")
    finally:
        context.finalize()


if __name__ == "__main__":
    main()
