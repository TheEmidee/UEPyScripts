from typing import TypedDict

Manifest = dict[str, str]  # {relative_path: blake3 hex digest}


class VersionManifest(TypedDict):
    files: Manifest  # every tracked file at this Version


class HashCacheEntry(TypedDict):
    fingerprint: str  # "mtime_ns:size"
    hash: str  # blake3 hex digest


class HashCacheManifest(TypedDict):
    commit_sha: str  # commit this cache was captured at
    files: dict[str, HashCacheEntry]
