from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import cast

import pytest

from tests.ugs.conftest import InMemoryStorage, WriteTree
from uepyscripts.tools.ugs.publish_store import PublishStore
from uepyscripts.tools.ugs.retention import RetentionRefusedError, retain_versions
from uepyscripts.tools.ugs.storage import Storage
from uepyscripts.tools.ugs.ugs_types import Manifest

GRACE = timedelta(hours=24)

Publish = Callable[..., None]


class UntouchableStorage:
    """Fails the test on any use, to prove a refusal happens before the Publish store is touched."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"Retention used the Publish store ({name}) before refusing")


@pytest.fixture
def store(storage: InMemoryStorage) -> PublishStore:
    return PublishStore(storage, jobs=1)


@pytest.fixture
def publish(store: PublishStore, write_tree: WriteTree, tmp_path: Path) -> Publish:
    """Publishes each version with one file of its own content."""

    def publish_versions(*versions: str) -> None:
        for version in versions:
            source = tmp_path / version
            store.publish(version, write_tree(source, {"a.dll": f"MZ {version}".encode()}), source)

    return publish_versions


def untouchable_store() -> PublishStore:
    return PublishStore(cast(Storage, UntouchableStorage()))


# ---- Refusals -------------------------------------------------------


def test_a_shallow_history_is_refused_before_the_publish_store_is_touched() -> None:
    with pytest.raises(RetentionRefusedError, match="shallow"):
        retain_versions(untouchable_store(), {"main": ["c2", "c1"]}, shallow=True, keep=30, blob_grace=GRACE)


def test_a_remote_without_branches_is_refused_before_the_publish_store_is_touched() -> None:
    with pytest.raises(RetentionRefusedError, match="branch"):
        retain_versions(untouchable_store(), {}, shallow=False, keep=30, blob_grace=GRACE)


@pytest.mark.parametrize("keep", [0, -1])
def test_keeping_fewer_than_one_version_per_branch_is_refused_before_the_publish_store_is_touched(keep: int) -> None:
    with pytest.raises(RetentionRefusedError, match="at least one"):
        retain_versions(untouchable_store(), {"main": ["c2", "c1"]}, shallow=False, keep=keep, blob_grace=GRACE)


# ---- Which Versions stay --------------------------------------------


def test_the_newest_versions_along_a_branch_are_kept_and_older_ones_removed(store: PublishStore, publish: Publish) -> None:
    publish("c1", "c2", "c3", "c4")

    outcome = retain_versions(store, {"main": ["c4", "c3", "c2", "c1"]}, shallow=False, keep=2, blob_grace=GRACE)

    assert outcome.published == {"c1", "c2", "c3", "c4"}
    assert outcome.kept == {"c3", "c4"}
    assert outcome.removed_versions == ["c1", "c2"]
    assert store.versions() == {"c3", "c4"}


def test_a_version_on_two_branches_is_kept_when_either_window_includes_it(store: PublishStore, publish: Publish) -> None:
    # c2 is old on main but the newest Version on the release branch cut from it
    publish("c1", "c2", "c3", "c4")
    ancestries = {"main": ["c4", "c3", "c2", "c1"], "release": ["c2", "c1"]}

    outcome = retain_versions(store, ancestries, shallow=False, keep=1, blob_grace=GRACE)

    assert outcome.kept == {"c4", "c2"}
    assert store.versions() == {"c4", "c2"}


def test_a_version_no_branch_reaches_is_removed(store: PublishStore, publish: Publish) -> None:
    publish("c1", "feature1")

    outcome = retain_versions(store, {"main": ["c1"]}, shallow=False, keep=30, blob_grace=GRACE)

    assert outcome.removed_versions == ["feature1"]
    assert store.versions() == {"c1"}


def test_commits_that_are_not_versions_do_not_use_up_the_window(store: PublishStore, publish: Publish) -> None:
    publish("c1", "c3")

    outcome = retain_versions(store, {"main": ["c5", "c4", "c3", "c2", "c1"]}, shallow=False, keep=2, blob_grace=GRACE)

    assert outcome.kept == {"c1", "c3"}
    assert outcome.removed_versions == []


# ---- Blobs ----------------------------------------------------------


@pytest.mark.parametrize(("blob_grace", "deleted"), [(GRACE, 1), (timedelta(days=365 * 100), 0)])
def test_blobs_only_removed_versions_reference_are_deleted_once_older_than_the_grace_period(
    store: PublishStore, storage: InMemoryStorage, write_tree: WriteTree, tmp_path: Path, blob_grace: timedelta, deleted: int
) -> None:
    manifests: dict[str, Manifest] = {}
    for version, files in (("c1", {"a.dll": b"MZ shared", "b.dll": b"MZ only c1"}), ("c2", {"a.dll": b"MZ shared"})):
        manifests[version] = write_tree(tmp_path / version, files)
        store.publish(version, manifests[version], tmp_path / version)

    outcome = retain_versions(store, {"main": ["c2", "c1"]}, shallow=False, keep=1, blob_grace=blob_grace)

    assert outcome.deleted_blobs == deleted
    assert f"blobs/{manifests['c2']['a.dll']}" in storage.keys("blobs/")
    assert (f"blobs/{manifests['c1']['b.dll']}" in storage.keys("blobs/")) == (deleted == 0)
