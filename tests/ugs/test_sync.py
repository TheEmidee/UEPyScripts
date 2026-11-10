import json
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest

from tests.ugs.conftest import InMemoryStorage, WriteTree
from uepyscripts.tools.ugs.publish_store import PublishStore
from uepyscripts.tools.ugs.sync import SYNC_STATE_FILE, SyncOutcome, sync_version
from uepyscripts.tools.ugs.ugs_types import Manifest

DLL_V1 = b"MZ" + b"engine code v1 " * 100
DLL_V2 = b"MZ" + b"engine code v2 " * 100
EXE = b"MZ" + b"editor " * 100
OLD = b"MZ" + b"removed later " * 100

Publish = Callable[[str, dict[str, bytes]], Manifest]


@pytest.fixture
def store(storage: InMemoryStorage) -> PublishStore:
    return PublishStore(storage, jobs=1)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    folder = tmp_path / "engine"
    folder.mkdir()
    return folder


@pytest.fixture
def publish(store: PublishStore, write_tree: WriteTree, tmp_path: Path) -> Publish:
    """Publishes `files` as a Version, from a folder of their own."""

    def publish_files(version: str, files: dict[str, bytes]) -> Manifest:
        source = tmp_path / "published" / version
        manifest = write_tree(source, files)
        store.publish(version, manifest, source)
        return manifest

    return publish_files


def read_tree(root: Path) -> dict[str, bytes]:
    return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file() and path.name != SYNC_STATE_FILE}


def sync_state(root: Path) -> dict[str, object]:
    return json.loads((root / SYNC_STATE_FILE).read_text())  # type: ignore[no-any-return]


def test_nothing_published_writes_nothing(store: PublishStore, root: Path) -> None:
    outcome = sync_version(store, root, ["c2", "c1"])

    assert outcome == SyncOutcome(version=None)
    assert list(root.iterdir()) == []


def test_first_sync_writes_every_file_of_the_nearest_version_and_saves_the_sync_state(store: PublishStore, publish: Publish, root: Path) -> None:
    publish("c1", {"Bin/old.dll": OLD})
    manifest = publish("c2", {"Bin/a.dll": DLL_V1, "Bin/b.exe": EXE})

    outcome = sync_version(store, root, ["c3", "c2", "c1"])

    assert outcome.version == "c2"
    assert sorted(outcome.downloaded) == ["Bin/a.dll", "Bin/b.exe"]
    assert read_tree(root) == {"Bin/a.dll": DLL_V1, "Bin/b.exe": EXE}
    assert sync_state(root) == {"version": "c2", "manifest": manifest}


def test_an_already_synced_version_downloads_nothing(store: PublishStore, publish: Publish, root: Path) -> None:
    publish("c1", {"Bin/a.dll": DLL_V1})
    sync_version(store, root, ["c1"])
    (root / "Bin" / "a.dll").unlink()

    outcome = sync_version(store, root, ["c1"])

    assert outcome == SyncOutcome(version="c1", already_synced=True)
    assert not (root / "Bin" / "a.dll").exists()


def test_a_later_sync_downloads_changed_files_and_deletes_removed_ones(store: PublishStore, publish: Publish, root: Path) -> None:
    publish("c1", {"Bin/a.dll": DLL_V1, "Bin/b.exe": EXE, "Bin/old.dll": OLD})
    sync_version(store, root, ["c1"])
    manifest = publish("c2", {"Bin/a.dll": DLL_V2, "Bin/b.exe": EXE})

    outcome = sync_version(store, root, ["c2", "c1"])

    assert outcome.downloaded == ["Bin/a.dll"]
    assert outcome.deleted == ["Bin/old.dll"]
    assert read_tree(root) == {"Bin/a.dll": DLL_V2, "Bin/b.exe": EXE}
    assert sync_state(root) == {"version": "c2", "manifest": manifest}


def test_without_a_version_in_the_ancestry_the_latest_version_is_synced(
    store: PublishStore, storage: InMemoryStorage, publish: Publish, root: Path
) -> None:
    publish("c1", {"Bin/a.dll": DLL_V1})
    storage.advance(timedelta(hours=1))
    publish("rewritten", {"Bin/a.dll": DLL_V2})

    outcome = sync_version(store, root, ["c9", "c8"])

    assert outcome.version == "rewritten"
    assert outcome.fell_back_to_latest
    assert read_tree(root) == {"Bin/a.dll": DLL_V2}


def test_an_unreadable_sync_state_counts_as_no_previous_sync(store: PublishStore, publish: Publish, root: Path) -> None:
    publish("c1", {"Bin/a.dll": DLL_V1, "Bin/b.exe": EXE})
    (root / SYNC_STATE_FILE).write_text('{"version": "c1", "manif')

    outcome = sync_version(store, root, ["c1"])

    assert not outcome.already_synced
    assert sorted(outcome.downloaded) == ["Bin/a.dll", "Bin/b.exe"]
    assert sync_state(root)["version"] == "c1"


def test_a_failed_download_keeps_the_previous_sync_state_and_deletes_nothing(
    store: PublishStore, storage: InMemoryStorage, publish: Publish, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish("c1", {"Bin/a.dll": DLL_V1, "Bin/old.dll": OLD})
    sync_version(store, root, ["c1"])
    state_before = sync_state(root)
    publish("c2", {"Bin/a.dll": DLL_V2})

    def fail(key: str, path: Path) -> None:
        raise OSError(f"network down while fetching {key}")

    monkeypatch.setattr(storage, "download_file", fail)

    with pytest.raises(OSError):
        sync_version(store, root, ["c2", "c1"])

    assert sync_state(root) == state_before
    assert read_tree(root) == {"Bin/a.dll": DLL_V1, "Bin/old.dll": OLD}
