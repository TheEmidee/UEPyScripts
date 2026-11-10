"""
The Publish store: every published Version, Blob, Hash cache and the
symbol-store manifest, kept in one bucket.

Layout (content-addressed):

  manifests/{sha}.json     {"files": {relative_path: blake3}}. A Version exists
                           exactly when its Manifest exists.
  blobs/{blake3}           zstd-compressed content of one file, keyed by the
                           hash of the uncompressed file. Shared by every
                           Version and branch that has the same file.
  hash_caches/{sha}.json   push-side fingerprints, a speed-up only.
  symstore-manifest.json   files last indexed into the symbol store.

Nobody outside this module knows a key. Write order is part of the interface:
Blobs are uploaded before the Manifest that references them, so a Version
never appears with missing content.
"""

import json
import os
import tempfile
import threading
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypeVar, cast

import zstandard

from uepyscripts import logger
from uepyscripts.tools.ugs.storage import Storage
from uepyscripts.tools.ugs.ugs_types import HashCacheManifest, Manifest, VersionManifest

MANIFESTS_PREFIX = "manifests/"
BLOBS_PREFIX = "blobs/"
HASH_CACHES_PREFIX = "hash_caches/"
SYMSTORE_MANIFEST_KEY = "symstore-manifest.json"

DEFAULT_JOBS = 32
DEFAULT_COMPRESSION_LEVEL = 10

T = TypeVar("T")
R = TypeVar("R")


@dataclass(frozen=True)
class PublishResult:
    uploaded_blobs: int
    reused_blobs: int


@dataclass(frozen=True)
class PruneResult:
    removed_versions: list[str]
    deleted_blobs: int


def _manifest_key(version: str) -> str:
    return f"{MANIFESTS_PREFIX}{version}.json"


def _blob_key(file_hash: str) -> str:
    return f"{BLOBS_PREFIX}{file_hash}"


def _hash_cache_key(version: str) -> str:
    return f"{HASH_CACHES_PREFIX}{version}.json"


def _name_after(prefix: str, key: str, suffix: str = "") -> str:
    name = key[len(prefix) :]
    return name[: -len(suffix)] if suffix and name.endswith(suffix) else name


def _encode_json(value: object) -> bytes:
    return json.dumps(value).encode()


class PublishStore:
    def __init__(self, storage: Storage, jobs: int = DEFAULT_JOBS, compression_level: int = DEFAULT_COMPRESSION_LEVEL) -> None:
        self._storage = storage
        self._jobs = max(1, jobs)
        self._compression_level = compression_level

    @property
    def jobs(self) -> int:
        """How many transfers run in parallel."""
        return self._jobs

    # ---- Versions -----------------------------------------------------

    def versions(self) -> set[str]:
        return {_name_after(MANIFESTS_PREFIX, obj.key, ".json") for obj in self._storage.list(MANIFESTS_PREFIX)}

    def nearest_version(self, ancestry: list[str]) -> str | None:
        """The first commit of `ancestry` (HEAD first) that is a Version."""
        published = self.versions()
        return next((sha for sha in ancestry if sha in published), None)

    def latest_version(self) -> str | None:
        """The most recently published Version, from any branch."""
        objects = self._storage.list(MANIFESTS_PREFIX)
        if not objects:
            return None
        newest = max(objects, key=lambda obj: obj.last_modified)
        return _name_after(MANIFESTS_PREFIX, newest.key, ".json")

    def manifest(self, version: str) -> Manifest:
        data = self._storage.read(_manifest_key(version))
        if data is None:
            raise KeyError(f"Version {version} is not published")
        return cast(VersionManifest, json.loads(data))["files"]

    def publish(self, version: str, manifest: Manifest, root: Path, baseline: Manifest | None = None) -> PublishResult:
        """Uploads every Blob the bucket doesn't have yet, read from `root`, then
        the Manifest. Hashes in `baseline` (the Manifest of an existing
        Version) are trusted to be present already; without one, the Blobs in
        the bucket are listed once."""
        path_for_hash: dict[str, str] = {}
        for path, file_hash in manifest.items():
            path_for_hash.setdefault(file_hash, path)

        if baseline is None:
            known = self._blob_hashes()
            missing = [h for h in path_for_hash if h not in known]
        else:
            known = set(baseline.values())
            candidates = [h for h in path_for_hash if h not in known]
            exists = self._parallel(lambda h: self._storage.exists(_blob_key(h)), candidates)
            missing = [h for h, present in zip(candidates, exists) if not present]

        logger.info(f"Uploading {len(missing)} new blob(s), reusing {len(path_for_hash) - len(missing)}")

        with tempfile.TemporaryDirectory(prefix="publish-blobs-") as tmp:
            tmp_dir = Path(tmp)
            self._parallel(lambda h: self._upload_blob(h, root / path_for_hash[h], tmp_dir), missing)

        payload: VersionManifest = {"files": manifest}
        self._storage.write(_manifest_key(version), _encode_json(payload))

        return PublishResult(uploaded_blobs=len(missing), reused_blobs=len(path_for_hash) - len(missing))

    def download(self, manifest: Manifest, paths: Iterable[str], root: Path) -> None:
        """Writes the content `manifest` gives each of `paths` under `root`,
        replacing what is there. Files are written next to their destination
        first, then moved over it."""
        paths = list(paths)
        logger.info(f"Downloading {len(paths)} file(s)")
        self._parallel(lambda p: self._download_blob(manifest[p], root / p), paths)

    def prune(self, remove: Iterable[str], blob_grace: timedelta, now: datetime | None = None) -> PruneResult:
        """Removes the Manifests of `remove`, then deletes every Blob that no
        remaining Manifest references and that is older than `blob_grace`. The
        grace period protects Blobs a push has uploaded but whose Manifest
        isn't written yet."""
        now = now or datetime.now(timezone.utc)
        published = self.versions()
        removed = sorted(published & set(remove))
        remaining = sorted(published - set(removed))

        self._storage.delete([_manifest_key(v) for v in removed])
        self._storage.delete([_hash_cache_key(v) for v in removed])

        referenced: set[str] = set()
        for files in self._parallel(self.manifest, remaining):
            referenced.update(files.values())

        cutoff = now - blob_grace
        garbage = [
            obj.key for obj in self._storage.list(BLOBS_PREFIX) if _name_after(BLOBS_PREFIX, obj.key) not in referenced and obj.last_modified < cutoff
        ]
        self._storage.delete(garbage)

        return PruneResult(removed_versions=removed, deleted_blobs=len(garbage))

    # ---- Hash caches --------------------------------------------------

    def latest_hash_cache(self, ancestry: list[str]) -> HashCacheManifest | None:
        """The Hash cache of the nearest commit in `ancestry`, else the newest
        one from any branch (a fingerprint mismatch only costs a re-hash).
        None when there is none or it can't be read."""
        objects = self._storage.list(HASH_CACHES_PREFIX)
        if not objects:
            return None

        by_sha = {_name_after(HASH_CACHES_PREFIX, obj.key, ".json"): obj for obj in objects}
        sha = next((s for s in ancestry if s in by_sha), None)
        if sha is None:
            sha = _name_after(HASH_CACHES_PREFIX, max(objects, key=lambda obj: obj.last_modified).key, ".json")

        try:
            data = self._storage.read(_hash_cache_key(sha))
            return cast(HashCacheManifest, json.loads(data)) if data is not None else None
        except Exception as e:
            logger.warning(f"Failed to read the hash cache of {sha} ({e})")
            return None

    def save_hash_cache(self, version: str, cache: HashCacheManifest, keep: int) -> None:
        """Saves `cache`, then keeps only the newest `keep` Hash caches."""
        key = _hash_cache_key(version)
        self._storage.write(key, _encode_json(cache))

        others = sorted(
            (obj for obj in self._storage.list(HASH_CACHES_PREFIX) if obj.key != key),
            key=lambda obj: obj.last_modified,
        )
        excess = len(others) + 1 - max(1, keep)
        if excess > 0:
            self._storage.delete([obj.key for obj in others[:excess]])

    # ---- Symbol store -------------------------------------------------

    def symstore_manifest(self) -> Manifest:
        data = self._storage.read(SYMSTORE_MANIFEST_KEY)
        return cast(Manifest, json.loads(data)) if data is not None else {}

    def save_symstore_manifest(self, manifest: Manifest) -> None:
        self._storage.write(SYMSTORE_MANIFEST_KEY, _encode_json(manifest))

    # ---- Internals ----------------------------------------------------

    def _blob_hashes(self) -> set[str]:
        return {_name_after(BLOBS_PREFIX, obj.key) for obj in self._storage.list(BLOBS_PREFIX)}

    def _upload_blob(self, file_hash: str, source: Path, tmp_dir: Path) -> None:
        compressed = tmp_dir / f"{file_hash}.zst"
        compressor = zstandard.ZstdCompressor(level=self._compression_level)
        with open(source, "rb") as fin, open(compressed, "wb") as fout:
            compressor.copy_stream(fin, fout)
        try:
            self._storage.upload_file(_blob_key(file_hash), compressed)
        finally:
            compressed.unlink(missing_ok=True)

    def _download_blob(self, file_hash: str, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        compressed = destination.with_name(f"{destination.name}.{threading.get_ident()}.zst")
        staged = destination.with_name(f"{destination.name}.{threading.get_ident()}.part")
        try:
            self._storage.download_file(_blob_key(file_hash), compressed)
            with open(compressed, "rb") as fin, open(staged, "wb") as fout:
                zstandard.ZstdDecompressor().copy_stream(fin, fout)
            os.replace(staged, destination)
        finally:
            compressed.unlink(missing_ok=True)
            staged.unlink(missing_ok=True)

    def _parallel(self, fn: Callable[[T], R], items: list[T]) -> list[R]:
        if not items:
            return []
        if self._jobs == 1 or len(items) == 1:
            return [fn(item) for item in items]
        with ThreadPoolExecutor(max_workers=self._jobs) as pool:
            return list(pool.map(fn, items))
