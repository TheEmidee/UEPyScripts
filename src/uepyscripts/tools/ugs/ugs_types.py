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


def diff_manifests(old: Manifest, new: Manifest) -> tuple[list[str], list[str]]:
    """The paths whose hash changed or that are new in `new`, and the paths of `old` that are gone from `new`."""
    changed = [path for path, file_hash in new.items() if old.get(path) != file_hash]
    removed = [path for path in old if path not in new]
    return changed, removed
