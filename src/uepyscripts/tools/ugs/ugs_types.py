from typing import TypedDict

Manifest = dict[str, str]


class VersionManifest(TypedDict):
    files: Manifest  # full state at this version: {relative_path: sha256}
    changed: list[str]  # files added or modified since the previous version
    removed: list[str]  # files removed since the previous version
