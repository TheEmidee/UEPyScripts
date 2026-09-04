from typing import TypedDict

Manifest = dict[str, str]


class VersionManifest(TypedDict):
    files: Manifest  # full state at this version: {relative_path: sha256}
    changed: list[str]  # files added or modified since the previous version
    removed: list[str]  # files removed since the previous version


class HashCacheEntry(TypedDict):
    fingerprint: str  # "mtime_ns:size"
    hash: str  # blake3 hex digest


class HashCacheManifest(TypedDict):
    commit_sha: str  # commit this cache was captured at
    files: dict[str, HashCacheEntry]
