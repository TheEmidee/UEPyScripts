import builtins
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

import blake3
import pytest

from uepyscripts.tools.ugs.storage import StoredObject
from uepyscripts.tools.ugs.ugs_types import Manifest

EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)


class InMemoryStorage:
    """Storage held in a dictionary. Every write is stamped by `clock` and
    recorded in `operations`, so tests can check write order."""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, datetime]] = {}
        self.operations: builtins.list[tuple[str, str]] = []
        self.now = EPOCH

    def advance(self, delta: timedelta) -> None:
        self.now += delta

    def read(self, key: str) -> bytes | None:
        entry = self.objects.get(key)
        return entry[0] if entry else None

    def write(self, key: str, data: bytes) -> None:
        self.operations.append(("write", key))
        self.objects[key] = (data, self.now)

    def upload_file(self, key: str, path: Path) -> None:
        self.operations.append(("upload", key))
        self.objects[key] = (path.read_bytes(), self.now)

    def download_file(self, key: str, path: Path) -> None:
        entry = self.objects.get(key)
        if entry is None:
            raise FileNotFoundError(key)
        path.write_bytes(entry[0])

    def exists(self, key: str) -> bool:
        self.operations.append(("exists", key))
        return key in self.objects

    def list(self, prefix: str) -> builtins.list[StoredObject]:
        return [StoredObject(key, stamp) for key, (_, stamp) in self.objects.items() if key.startswith(prefix)]

    def delete(self, keys: builtins.list[str]) -> None:
        for key in keys:
            self.operations.append(("delete", key))
            self.objects.pop(key, None)

    def keys(self, prefix: str = "") -> set[str]:
        return {key for key in self.objects if key.startswith(prefix)}


@pytest.fixture
def storage() -> InMemoryStorage:
    return InMemoryStorage()


WriteTree = Callable[[Path, dict[str, bytes]], Manifest]


def _write_tree(root: Path, files: dict[str, bytes]) -> Manifest:
    """Writes `files` under `root` and returns their Manifest."""
    manifest: Manifest = {}
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        manifest[rel] = blake3.blake3(content).hexdigest()
    return manifest


@pytest.fixture
def write_tree() -> WriteTree:
    return _write_tree
