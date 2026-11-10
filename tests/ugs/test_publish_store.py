import json
from datetime import timedelta
from pathlib import Path

import pytest

from tests.ugs.conftest import InMemoryStorage, WriteTree
from uepyscripts.tools.ugs.cleanup import select_versions_to_keep
from uepyscripts.tools.ugs.publish_store import PublishStore
from uepyscripts.tools.ugs.storage import DryRunStorage
from uepyscripts.tools.ugs.ugs_types import HashCacheManifest, diff_manifests

DLL = b"MZ" + b"engine code " * 1000
EXE = b"MZ" + b"editor " * 500
LIB = b"!<arch>" + b"symbols " * 800


def make_store(storage: InMemoryStorage) -> PublishStore:
    return PublishStore(storage, jobs=4)


def hash_cache(sha: str) -> HashCacheManifest:
    return {"commit_sha": sha, "files": {"Engine/a.dll": {"fingerprint": "1:2", "hash": "abc"}}}


# ---- publish ---------------------------------------------------------


def test_publish_then_download_restores_identical_files(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    store = make_store(storage)
    manifest = write_tree(tmp_path / "ci", {"Engine/Binaries/a.dll": DLL, "Engine/Binaries/b.exe": EXE})

    store.publish("v1", manifest, tmp_path / "ci")
    store.download(store.manifest("v1"), manifest.keys(), tmp_path / "dev")

    assert (tmp_path / "dev/Engine/Binaries/a.dll").read_bytes() == DLL
    assert (tmp_path / "dev/Engine/Binaries/b.exe").read_bytes() == EXE


def test_publish_stores_blobs_compressed_and_keyed_by_content_hash(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    manifest = write_tree(tmp_path, {"a.dll": DLL})

    make_store(storage).publish("v1", manifest, tmp_path)

    blob = storage.read(f"blobs/{manifest['a.dll']}")
    assert blob is not None
    assert len(blob) < len(DLL)


def test_publish_writes_the_manifest_after_every_blob(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    manifest = write_tree(tmp_path, {"a.dll": DLL, "b.exe": EXE, "c.lib": LIB})

    make_store(storage).publish("v1", manifest, tmp_path)

    writes = [key for op, key in storage.operations if op in ("upload", "write")]
    assert writes[-1] == "manifests/v1.json"
    assert len(writes) == 4


def test_publish_uploads_identical_files_once(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    manifest = write_tree(tmp_path, {"Engine/a.dll": DLL, "Game/a.dll": DLL})

    result = make_store(storage).publish("v1", manifest, tmp_path)

    assert result.uploaded_blobs == 1
    assert storage.keys("blobs/") == {f"blobs/{manifest['Engine/a.dll']}"}


def test_publish_without_baseline_skips_blobs_already_in_the_bucket(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    store = make_store(storage)
    store.publish("v1", write_tree(tmp_path / "1", {"a.dll": DLL}), tmp_path / "1")

    result = store.publish("v2", write_tree(tmp_path / "2", {"a.dll": DLL, "b.exe": EXE}), tmp_path / "2")

    assert (result.uploaded_blobs, result.reused_blobs) == (1, 1)


def test_publish_with_baseline_only_checks_hashes_the_baseline_lacks(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    store = make_store(storage)
    v1 = write_tree(tmp_path / "1", {"a.dll": DLL, "b.exe": EXE})
    store.publish("v1", v1, tmp_path / "1")
    storage.operations.clear()

    v2 = write_tree(tmp_path / "2", {"a.dll": DLL, "b.exe": EXE, "c.lib": LIB})
    result = store.publish("v2", v2, tmp_path / "2", baseline=store.manifest("v1"))

    checked = [key for op, key in storage.operations if op == "exists"]
    assert checked == [f"blobs/{v2['c.lib']}"]
    assert (result.uploaded_blobs, result.reused_blobs) == (1, 2)


# ---- versions --------------------------------------------------------


def test_a_version_exists_once_its_manifest_is_written(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    store = make_store(storage)
    assert store.versions() == set()

    store.publish("v1", write_tree(tmp_path, {"a.dll": DLL}), tmp_path)

    assert store.versions() == {"v1"}
    assert json.loads(storage.read("manifests/v1.json") or b"") == {"files": store.manifest("v1")}


def test_nearest_version_is_the_first_published_commit_of_the_ancestry(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    store = make_store(storage)
    manifest = write_tree(tmp_path, {"a.dll": DLL})
    store.publish("old", manifest, tmp_path)
    store.publish("mid", manifest, tmp_path)

    assert store.nearest_version(["head", "mid", "old"]) == "mid"
    assert store.nearest_version(["unrelated"]) is None


def test_latest_version_is_the_most_recently_published(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    store = make_store(storage)
    manifest = write_tree(tmp_path, {"a.dll": DLL})
    assert store.latest_version() is None

    store.publish("b", manifest, tmp_path)
    storage.advance(timedelta(minutes=1))
    store.publish("a", manifest, tmp_path)

    assert store.latest_version() == "a"


def test_reading_the_manifest_of_an_unpublished_version_raises(storage: InMemoryStorage) -> None:
    with pytest.raises(KeyError):
        make_store(storage).manifest("nope")


# ---- download --------------------------------------------------------


def test_download_replaces_existing_files_and_creates_folders(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    store = make_store(storage)
    manifest = write_tree(tmp_path / "ci", {"Engine/a.dll": DLL, "Engine/New/b.exe": EXE})
    store.publish("v1", manifest, tmp_path / "ci")
    write_tree(tmp_path / "dev", {"Engine/a.dll": b"stale"})

    store.download(manifest, ["Engine/a.dll", "Engine/New/b.exe"], tmp_path / "dev")

    assert (tmp_path / "dev/Engine/a.dll").read_bytes() == DLL
    assert (tmp_path / "dev/Engine/New/b.exe").read_bytes() == EXE
    assert sorted(p.name for p in (tmp_path / "dev/Engine").iterdir()) == ["New", "a.dll"]


# ---- prune -----------------------------------------------------------


def test_prune_deletes_removed_manifests_hash_caches_and_unreferenced_blobs(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    store = make_store(storage)
    v1 = write_tree(tmp_path / "1", {"a.dll": DLL, "b.exe": EXE})
    store.publish("v1", v1, tmp_path / "1")
    store.save_hash_cache("v1", hash_cache("v1"), keep=10)
    v2 = write_tree(tmp_path / "2", {"a.dll": DLL, "c.lib": LIB})
    store.publish("v2", v2, tmp_path / "2")
    storage.advance(timedelta(days=2))

    result = store.prune({"v1"}, blob_grace=timedelta(hours=24), now=storage.now)

    assert result.removed_versions == ["v1"]
    assert result.deleted_blobs == 1
    assert store.versions() == {"v2"}
    assert storage.keys("hash_caches/") == set()
    assert storage.keys("blobs/") == {f"blobs/{v2['a.dll']}", f"blobs/{v2['c.lib']}"}


def test_prune_keeps_unreferenced_blobs_younger_than_the_grace_period(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    store = make_store(storage)
    store.publish("v1", write_tree(tmp_path, {"a.dll": DLL}), tmp_path)
    storage.advance(timedelta(hours=1))

    result = store.prune({"v1"}, blob_grace=timedelta(hours=24), now=storage.now)

    assert result.deleted_blobs == 0
    assert len(storage.keys("blobs/")) == 1


def test_prune_ignores_versions_that_are_not_published(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    store = make_store(storage)
    store.publish("v1", write_tree(tmp_path, {"a.dll": DLL}), tmp_path)

    result = store.prune({"ghost"}, blob_grace=timedelta(0), now=storage.now + timedelta(seconds=1))

    assert result.removed_versions == []
    assert result.deleted_blobs == 0


def test_dry_run_prune_reports_the_same_result_without_deleting(storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path) -> None:
    make_store(storage).publish("v1", write_tree(tmp_path / "1", {"a.dll": DLL}), tmp_path / "1")
    make_store(storage).publish("v2", write_tree(tmp_path / "2", {"b.exe": EXE}), tmp_path / "2")
    storage.advance(timedelta(days=2))
    before = set(storage.objects)

    result = PublishStore(DryRunStorage(storage)).prune({"v1"}, blob_grace=timedelta(hours=24), now=storage.now)

    assert (result.removed_versions, result.deleted_blobs) == (["v1"], 1)
    assert set(storage.objects) == before


# ---- hash caches -----------------------------------------------------


def test_save_hash_cache_keeps_only_the_newest(storage: InMemoryStorage) -> None:
    store = make_store(storage)
    for sha in ["c1", "c2", "c3", "c4"]:
        store.save_hash_cache(sha, hash_cache(sha), keep=2)
        storage.advance(timedelta(minutes=1))

    assert storage.keys("hash_caches/") == {"hash_caches/c3.json", "hash_caches/c4.json"}


def test_latest_hash_cache_prefers_the_nearest_ancestor(storage: InMemoryStorage) -> None:
    store = make_store(storage)
    store.save_hash_cache("ancestor", hash_cache("ancestor"), keep=10)
    storage.advance(timedelta(minutes=1))
    store.save_hash_cache("other-branch", hash_cache("other-branch"), keep=10)

    cache = store.latest_hash_cache(["head", "ancestor"])

    assert cache is not None and cache["commit_sha"] == "ancestor"


def test_latest_hash_cache_falls_back_to_the_newest_from_any_branch(storage: InMemoryStorage) -> None:
    store = make_store(storage)
    store.save_hash_cache("old", hash_cache("old"), keep=10)
    storage.advance(timedelta(minutes=1))
    store.save_hash_cache("new", hash_cache("new"), keep=10)

    cache = store.latest_hash_cache(["unrelated"])

    assert cache is not None and cache["commit_sha"] == "new"


def test_latest_hash_cache_is_none_when_missing_or_unreadable(storage: InMemoryStorage) -> None:
    store = make_store(storage)
    assert store.latest_hash_cache(["head"]) is None

    storage.write("hash_caches/head.json", b"not json")

    assert store.latest_hash_cache(["head"]) is None


# ---- symbol store ----------------------------------------------------


def test_symstore_manifest_defaults_to_empty_and_round_trips(storage: InMemoryStorage) -> None:
    store = make_store(storage)
    assert store.symstore_manifest() == {}

    store.save_symstore_manifest({"a.pdb": "h"})

    assert store.symstore_manifest() == {"a.pdb": "h"}


# ---- callers' pure decisions -----------------------------------------


def test_diff_manifests_lists_changed_and_removed_paths() -> None:
    to_download, to_delete = diff_manifests({"a": "1", "b": "2", "gone": "3"}, {"a": "1", "b": "changed", "new": "4"})

    assert sorted(to_download) == ["b", "new"]
    assert to_delete == ["gone"]


def test_select_versions_to_keep_keeps_the_newest_per_branch() -> None:
    published = {"m3", "m2", "m1", "f2", "orphan"}
    ancestries = {
        "main": ["m4", "m3", "x", "m2", "m1"],
        "feature": ["f2", "f1", "m2", "m1"],
    }

    assert select_versions_to_keep(published, ancestries, keep=2) == {"m3", "m2", "f2"}
