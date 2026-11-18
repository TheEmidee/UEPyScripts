"""
Publishing a Version: the Tracked files of the engine tree at one commit go to
the Publish store (see publish_store.py). The symbol files that changed are
indexed into the symbol store, and with upload_symbols the PDBs also go to the
Publish store, as the Version's Symbols manifest. Both can be done in one run.

`publish_version` is the whole workflow, in this order:
  1. stop if the commit is already a Version (with force_symbol_index, index
     its symbol files first, as in step 7; with upload_symbols, publish its
     Symbols manifest first, as in step 5, unless it already has one)
  2. scan the Tracked files, reusing hashes from the nearest Hash cache when a
     file's mtime and size haven't changed
  3. diff against the nearest Version in the ancestry (the baseline)
  4. with skip_upload, stop and report the diff
  5. with upload_symbols, upload the missing PDB Blobs, then the Symbols
     manifest
  6. upload the missing Blobs, then the Manifest
  7. with a symbol indexer, index the symbol files that changed since the last
     indexing (every symbol file with force_symbol_index), then record them
  8. save the Hash cache, holding only the files seen in this run

The Symbols manifest is written before the Manifest, so a Version that has
symbols has them as soon as it exists.

Git, the command line and output files stay with the caller. Retention is
ugs.cleanup's job, never this module's.
"""

import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import blake3

from uepyscripts import logger
from uepyscripts.tools.ugs.publish_store import PublishStore
from uepyscripts.tools.ugs.ugs_types import HashCacheEntry, HashCacheManifest, Manifest, diff_manifests

DEFAULT_KEEP_HASH_CACHES = 100

SYMSTORE_EXECUTABLE = Path(r"C:\Program Files (x86)\Windows Kits\10\Debuggers\x64\symstore.exe")


@dataclass(frozen=True)
class TrackedFiles:
    """Which files of the tree make up a Version. Every path and pattern is
    relative to the root folder being published.

    `directories` are walked for files with one of `extensions` (or, for the
    symbol store, `symbol_extensions`), skipping `ignored_folders` below them.
    An entry with wildcards, such as a trailing `**/`, is expanded with
    Path.glob first. `glob_files` are taken as they match, even inside an
    ignored folder, since an explicit pattern is an explicit request. Files
    whose stem matches one of `ignored_stem_patterns` are always left out."""

    directories: tuple[str, ...]
    glob_files: tuple[str, ...] = ()
    extensions: frozenset[str] = frozenset({".dll", ".exe", ".lib", ".modules", ".target"})
    # PDBs are the point of the symbol store; DLL/EXE ride along so minidumps
    # and remote debugging resolve both code and symbols from one place.
    # Only the ones that aren't Tracked files (the PDBs) go to the Symbols
    # manifest: the others are in the Manifest already.
    symbol_extensions: frozenset[str] = frozenset({".pdb", ".dll", ".exe"})
    ignored_folders: frozenset[str] = frozenset({"Intermediate"})
    # Hot-reload leftovers: `.patch_` followed by digits at the end of the stem
    ignored_stem_patterns: tuple[re.Pattern[str], ...] = (re.compile(r"\.patch_\d+$"),)


ENGINE_TRACKED_FILES = TrackedFiles(
    directories=(
        "Engine/Binaries/Win64",
        "Engine/Plugins",
        "Engine/Platforms",
        "Engine/Intermediate/Build/BuildRules",
        "Engine/Intermediate/Build/Win64/**/",
        "Engine/Plugins/**/Intermediate/**/",
    ),
    glob_files=(
        "Engine/Intermediate/Build/BuildRules/*.json",
        "Engine/Intermediate/Build/Win64/**/*.h",
        "Engine/Intermediate/Build/Win64/**/*.natvis",
        "Engine/Plugins/**/Intermediate/**/*.h",
        "Engine/Plugins/**/Intermediate/**/*.natvis",
    ),
)


class SymbolIndexer(Protocol):
    def index(self, files: list[Path]) -> None:
        """Adds these files to the symbol store. Raises when it can't."""
        ...


class SymStoreIndexer:
    """Indexes files into a Windows symbol store folder with symstore.exe."""

    def __init__(self, store_path: str, product: str, executable: Path = SYMSTORE_EXECUTABLE) -> None:
        self._store_path = store_path
        self._product = product
        self._executable = executable

    def index(self, files: list[Path]) -> None:
        with tempfile.TemporaryDirectory(prefix="symstore-") as tmp:
            list_file = Path(tmp) / "files.txt"
            list_file.write_text("\n".join(str(f.resolve()) for f in files), encoding="utf-8")
            result = subprocess.run(
                [str(self._executable), "add", "/f", f"@{list_file}", "/s", self._store_path, "/t", self._product],
                capture_output=True,
                text=True,
            )

        if result.returncode != 0:
            raise RuntimeError(f"symstore add failed with exit code {result.returncode}:\n{result.stdout}\n{result.stderr}")


@dataclass(frozen=True)
class PublishOutcome:
    """What publish_version did. When `already_published`, no Version data was
    scanned or written and every other field is empty, except
    `indexed_symbol_files` when symbol indexing was forced and
    `published_symbol_files` when the Version had no Symbols manifest yet.
    `published_symbol_files` is how many files the Symbols manifest written by
    this run lists (0 when none was written)."""

    already_published: bool = False
    baseline: str | None = None
    changed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    uploaded_blobs: int = 0
    reused_blobs: int = 0
    indexed_symbol_files: int = 0
    published_symbol_files: int = 0


def publish_version(
    store: PublishStore,
    tracked_files: TrackedFiles,
    root: Path,
    commit: str,
    ancestry: list[str],
    *,
    symbol_indexer: SymbolIndexer | None = None,
    skip_upload: bool = False,
    keep_hash_caches: int = DEFAULT_KEEP_HASH_CACHES,
    force_symbol_index: bool = False,
    upload_symbols: bool = False,
) -> PublishOutcome:
    """Publishes `commit` as a Version from the files under `root`.

    `ancestry` is HEAD's ancestry, newest first; its nearest Version is the
    baseline. Without `symbol_indexer`, the symbol store is left alone. With
    `force_symbol_index`, every symbol file is indexed, even when `commit` is
    already a Version or the files were indexed before. With `upload_symbols`,
    the PDBs are published as the Version's Symbols manifest, also when
    `commit` is already a Version that has none. With `skip_upload`, the diff
    is computed and nothing is written."""
    baseline_version = store.nearest_version(ancestry)
    if baseline_version == commit:
        if skip_upload:
            return PublishOutcome(already_published=True, baseline=commit)

        force_index = force_symbol_index and symbol_indexer is not None
        backfill_symbols = upload_symbols and store.symbols_manifest(commit) is None
        indexed = 0
        published_symbols = 0
        if backfill_symbols or force_index:
            hasher = _CachedHasher(store.latest_hash_cache(ancestry))
            if backfill_symbols:
                published_symbols = _publish_symbols(store, tracked_files, root, commit, hasher, baseline=None)
            if force_index:
                assert symbol_indexer is not None
                indexed = _index_symbols(store, tracked_files, root, hasher, symbol_indexer, force=True)
        return PublishOutcome(already_published=True, baseline=commit, indexed_symbol_files=indexed, published_symbol_files=published_symbols)

    hasher = _CachedHasher(store.latest_hash_cache(ancestry))

    logger.info("Scan file states")
    manifest = _scan_by_extension(root, tracked_files, tracked_files.extensions, hasher)
    manifest.update(_scan_by_glob(root, tracked_files, hasher))
    logger.info(f"Finished scan. Found {len(manifest)} files.")

    baseline: Manifest | None = None
    if baseline_version is None:
        logger.info("No published ancestor — publishing every file")
    else:
        logger.info(f"Using {baseline_version} as baseline")
        baseline = store.manifest(baseline_version)

    changed, removed = diff_manifests(baseline or {}, manifest)
    logger.info(f"{len(changed)} changed, {len(removed)} removed since the baseline")

    if skip_upload:
        return PublishOutcome(baseline=baseline_version, changed=changed, removed=removed)

    published_symbols = 0
    if upload_symbols:
        symbols_baseline = store.symbols_manifest(baseline_version) if baseline_version is not None else None
        published_symbols = _publish_symbols(store, tracked_files, root, commit, hasher, baseline=symbols_baseline)

    result = store.publish(commit, manifest, root, baseline=baseline)

    indexed = 0
    if symbol_indexer is not None:
        indexed = _index_symbols(store, tracked_files, root, hasher, symbol_indexer, force=force_symbol_index)

    logger.info("Upload hash cache")
    store.save_hash_cache(commit, hasher.hash_cache(commit), keep=keep_hash_caches)

    return PublishOutcome(
        baseline=baseline_version,
        changed=changed,
        removed=removed,
        uploaded_blobs=result.uploaded_blobs,
        reused_blobs=result.reused_blobs,
        indexed_symbol_files=indexed,
        published_symbol_files=published_symbols,
    )


# ---- Internals --------------------------------------------------------


def _index_symbols(
    store: PublishStore,
    tracked_files: TrackedFiles,
    root: Path,
    hasher: "_CachedHasher",
    symbol_indexer: SymbolIndexer,
    *,
    force: bool,
) -> int:
    """Indexes the symbol files that changed since the last indexing (all of
    them with `force`), records them, and returns how many were indexed."""
    logger.info("Scan file states for debug files")
    symbols = _scan_by_extension(root, tracked_files, tracked_files.symbol_extensions, hasher)
    symbols_changed, _ = diff_manifests({} if force else store.symstore_manifest(), symbols)

    if symbols_changed:
        logger.info(f"Indexing {len(symbols_changed)} file(s) into the symbol store")
        symbol_indexer.index([root / path for path in symbols_changed])
        store.save_symstore_manifest(symbols)
    else:
        logger.info("No changes for the symbol store")
    return len(symbols_changed)


def _publish_symbols(
    store: PublishStore,
    tracked_files: TrackedFiles,
    root: Path,
    commit: str,
    hasher: "_CachedHasher",
    *,
    baseline: Manifest | None,
) -> int:
    """Publishes the symbol files that aren't Tracked files (the PDBs) as the
    Symbols manifest of `commit`, and returns how many it lists. `baseline`
    is the Symbols manifest of the baseline Version, if it has one."""
    logger.info("Scan file states for symbol files to upload to S3")
    symbols = _scan_by_extension(root, tracked_files, tracked_files.symbol_extensions - tracked_files.extensions, hasher)
    logger.info(f"Uploading {len(symbols)} symbol file(s) to S3")
    store.publish_symbols(commit, symbols, root, baseline=baseline)
    return len(symbols)


class _CachedHasher:
    """Hashes files, reusing the previous Hash cache's hash when a file's
    mtime and size are unchanged. Remembers only the files it was asked
    about, so the next Hash cache drops files that are gone."""

    def __init__(self, previous: HashCacheManifest | None) -> None:
        self._previous: dict[str, HashCacheEntry] = previous["files"] if previous else {}
        self._seen: dict[str, HashCacheEntry] = {}
        if previous:
            logger.info(f"Seeded hash cache from {previous['commit_sha']} ({len(self._previous)} entries)")
        else:
            logger.info("No hash cache found — starting with a cold hash cache")

    def hash(self, path: Path, rel: str) -> str:
        stat = path.stat()
        fingerprint = f"{stat.st_mtime_ns}:{stat.st_size}"

        # Symbol files can be scanned twice in one run: for S3 and for the symbol store
        cached = self._seen.get(rel) or self._previous.get(rel)
        if cached and cached["fingerprint"] == fingerprint:
            file_hash = cached["hash"]
        else:
            # blake3 picks single-threaded hashing for small files on its own
            file_hash = blake3.blake3(max_threads=blake3.blake3.AUTO).update_mmap(str(path)).hexdigest()

        self._seen[rel] = {"fingerprint": fingerprint, "hash": file_hash}
        return file_hash

    def hash_cache(self, commit: str) -> HashCacheManifest:
        return {"commit_sha": commit, "files": dict(self._seen)}


def _is_ignored_file(path: Path, tracked_files: TrackedFiles) -> bool:
    return any(pattern.search(path.stem) for pattern in tracked_files.ignored_stem_patterns)


def _expand_directories(root: Path, patterns: tuple[str, ...]) -> list[Path]:
    directories: list[Path] = []
    for pattern in patterns:
        if any(ch in pattern for ch in "*?["):
            matches = [match for match in root.glob(pattern) if match.is_dir()]
        else:
            matches = [root / pattern] if (root / pattern).exists() else []

        for match in matches:
            if match not in directories:
                directories.append(match)

    return directories


def _scan_by_extension(root: Path, tracked_files: TrackedFiles, extensions: frozenset[str], hasher: _CachedHasher) -> Manifest:
    manifest: Manifest = {}
    for base in _expand_directories(root, tracked_files.directories):
        for folder, subfolders, files in os.walk(base):
            subfolders[:] = [name for name in subfolders if name not in tracked_files.ignored_folders]

            for file_name in files:
                path = Path(folder) / file_name
                if path.suffix.lower() not in extensions or _is_ignored_file(path, tracked_files):
                    continue

                rel = path.relative_to(root).as_posix()
                manifest[rel] = hasher.hash(path, rel)

    return manifest


def _scan_by_glob(root: Path, tracked_files: TrackedFiles, hasher: _CachedHasher) -> Manifest:
    manifest: Manifest = {}
    for pattern in tracked_files.glob_files:
        for path in root.glob(pattern):
            if not path.is_file() or _is_ignored_file(path, tracked_files):
                continue

            rel = path.relative_to(root).as_posix()
            manifest[rel] = hasher.hash(path, rel)

    return manifest
