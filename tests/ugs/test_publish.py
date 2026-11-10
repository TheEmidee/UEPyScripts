import json
import os
import sys
from pathlib import Path

import pytest

from tests.ugs.conftest import InMemoryStorage, WriteTree
from uepyscripts.tools.ugs.publish import PublishOutcome, SymStoreIndexer, TrackedFiles, publish_version
from uepyscripts.tools.ugs.publish_store import PublishStore
from uepyscripts.tools.ugs.ugs_types import HashCacheManifest, Manifest

DLL = b"MZ" + b"engine code " * 200
EXE = b"MZ" + b"editor " * 100
PDB = b"Microsoft C/C++ MSF " * 50

TRACKED = TrackedFiles(directories=("Bin",), glob_files=("Bin/Intermediate/*.json",))


class RecordingIndexer:
    def __init__(self) -> None:
        self.calls: list[list[Path]] = []

    def index(self, files: list[Path]) -> None:
        self.calls.append(files)


@pytest.fixture
def store(storage: InMemoryStorage) -> PublishStore:
    return PublishStore(storage, jobs=1)


def publish(store: PublishStore, root: Path, commit: str, ancestry: list[str], **kwargs: object) -> PublishOutcome:
    return publish_version(store, TRACKED, root, commit, [commit, *ancestry], **kwargs)  # type: ignore[arg-type]


def uploads(storage: InMemoryStorage) -> list[str]:
    return [key for op, key in storage.operations if op == "upload"]


def writes(storage: InMemoryStorage) -> list[tuple[str, str]]:
    return [(op, key) for op, key in storage.operations if op in ("upload", "write", "delete")]


def saved_hash_cache(storage: InMemoryStorage, commit: str) -> HashCacheManifest:
    data = storage.read(f"hash_caches/{commit}.json")
    assert data is not None
    return json.loads(data)  # type: ignore[no-any-return]


def test_a_commit_that_is_already_a_version_is_left_alone(
    store: PublishStore, storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path
) -> None:
    write_tree(tmp_path, {"Bin/a.dll": DLL})
    publish(store, tmp_path, "c1", [])
    storage.operations.clear()

    outcome = publish(store, tmp_path, "c1", [], symbol_indexer=RecordingIndexer())

    assert outcome == PublishOutcome(already_published=True, baseline="c1")
    assert storage.operations == []


def test_first_publish_uploads_every_blob_then_the_manifest(
    store: PublishStore, storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path
) -> None:
    manifest = write_tree(tmp_path, {"Bin/a.dll": DLL, "Bin/b.exe": EXE})

    outcome = publish(store, tmp_path, "c1", ["older"])

    assert outcome.baseline is None
    assert sorted(outcome.changed) == ["Bin/a.dll", "Bin/b.exe"]
    assert outcome.uploaded_blobs == 2
    assert store.manifest("c1") == manifest
    assert [key for _, key in writes(storage)][2] == "manifests/c1.json"


def test_publish_against_a_baseline_uploads_only_changed_content(
    store: PublishStore, storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path
) -> None:
    write_tree(tmp_path, {"Bin/a.dll": DLL, "Bin/b.exe": EXE, "Bin/gone.dll": b"MZ old"})
    publish(store, tmp_path, "c1", [])
    storage.operations.clear()

    (tmp_path / "Bin/gone.dll").unlink()
    manifest = write_tree(tmp_path, {"Bin/a.dll": DLL + b"patched", "Bin/new.dll": EXE})

    outcome = publish(store, tmp_path, "c2", ["c1"])

    assert outcome.baseline == "c1"
    assert sorted(outcome.changed) == ["Bin/a.dll", "Bin/new.dll"]
    assert outcome.removed == ["Bin/gone.dll"]
    assert uploads(storage) == [f"blobs/{manifest['Bin/a.dll']}"]  # new.dll has the same content as b.exe
    assert outcome.reused_blobs == 1  # one Blob per distinct content


def test_skip_upload_reports_the_diff_and_writes_nothing(
    store: PublishStore, storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path
) -> None:
    write_tree(tmp_path, {"Bin/a.dll": DLL, "Bin/a.pdb": PDB})

    outcome = publish(store, tmp_path, "c1", [], symbol_indexer=RecordingIndexer(), skip_upload=True)

    assert outcome.changed == ["Bin/a.dll"]
    assert writes(storage) == []


def test_only_symbol_files_changed_since_the_last_indexing_are_indexed(
    store: PublishStore, storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path
) -> None:
    write_tree(tmp_path, {"Bin/a.dll": DLL, "Bin/a.pdb": PDB, "Bin/a.lib": b"!<arch>"})
    indexer = RecordingIndexer()
    publish(store, tmp_path, "c1", [], symbol_indexer=indexer)

    write_tree(tmp_path, {"Bin/a.pdb": PDB + b"rebuilt"})
    outcome = publish(store, tmp_path, "c2", ["c1"], symbol_indexer=indexer)

    assert [sorted(call) for call in indexer.calls] == [
        [tmp_path / "Bin/a.dll", tmp_path / "Bin/a.pdb"],
        [tmp_path / "Bin/a.pdb"],
    ]
    assert outcome.indexed_symbol_files == 1
    assert sorted(store.symstore_manifest()) == ["Bin/a.dll", "Bin/a.pdb"]


def test_without_an_indexer_the_symbol_store_is_left_alone(
    store: PublishStore, storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path
) -> None:
    write_tree(tmp_path, {"Bin/a.dll": DLL, "Bin/a.pdb": PDB})

    outcome = publish(store, tmp_path, "c1", [])

    assert outcome.indexed_symbol_files == 0
    assert storage.keys("symstore") == set()


def test_a_file_with_unchanged_mtime_and_size_keeps_its_cached_hash(
    store: PublishStore, storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path
) -> None:
    manifest = write_tree(tmp_path, {"Bin/a.dll": DLL})
    publish(store, tmp_path, "c1", [])

    dll = tmp_path / "Bin/a.dll"
    stat = dll.stat()
    dll.write_bytes(DLL.replace(b"engine", b"ENGINE"))
    os.utime(dll, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    outcome = publish(store, tmp_path, "c2", ["c1"])

    assert outcome.changed == []
    assert store.manifest("c2") == manifest


def test_the_saved_hash_cache_holds_only_the_files_seen_this_run(
    store: PublishStore, storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path
) -> None:
    write_tree(tmp_path, {"Bin/a.dll": DLL, "Bin/b.dll": EXE})
    publish(store, tmp_path, "c1", [])

    (tmp_path / "Bin/b.dll").unlink()
    publish(store, tmp_path, "c2", ["c1"])

    cache = saved_hash_cache(storage, "c2")
    assert cache["commit_sha"] == "c2"
    assert list(cache["files"]) == ["Bin/a.dll"]


def test_ignored_folders_patch_files_and_other_extensions_are_not_tracked_but_explicit_globs_are(
    store: PublishStore, write_tree: WriteTree, tmp_path: Path
) -> None:
    write_tree(
        tmp_path,
        {
            "Bin/a.dll": DLL,
            "Bin/a.patch_12.dll": DLL,
            "Bin/notes.txt": b"text",
            "Bin/Intermediate/hidden.dll": DLL,
            "Bin/Intermediate/rules.json": b"{}",
            "Elsewhere/b.dll": DLL,
        },
    )

    publish(store, tmp_path, "c1", [])

    manifest: Manifest = store.manifest("c1")
    assert sorted(manifest) == ["Bin/Intermediate/rules.json", "Bin/a.dll"]


def test_symstore_indexer_reports_symstore_output_on_failure(tmp_path: Path) -> None:
    # The Python interpreter stands in for symstore.exe: it fails on the "add" argument
    indexer = SymStoreIndexer(str(tmp_path / "store"), "Game", executable=Path(sys.executable))

    with pytest.raises(RuntimeError, match="symstore add failed with exit code"):
        indexer.index([tmp_path / "a.pdb"])
