from pathlib import Path

import pytest

from uepyscripts.internal.config import ConfigError
from uepyscripts.internal.workspace import Workspace
from uepyscripts.tools.ci import cleanup as ci_cleanup
from uepyscripts.tools.ci.shared_storage import SharedStorage


def workspace(game: Path) -> Workspace:
    return Workspace(game / "Game.uproject")


def test_the_path_is_the_configured_folder_joined_with_the_build_tag(game: Path, tmp_path: Path) -> None:
    storage = SharedStorage.for_build(workspace(game), "jenkins-42")

    assert storage.path == tmp_path / "Storage" / "jenkins-42"


def test_a_missing_jenkins_key_raises_a_config_error(game: Path) -> None:
    (game / "Config" / "PyScripts" / "config.ini").write_text("[Project]\nBuildgraphPath = Build/Graph.xml\n")

    with pytest.raises(ConfigError) as error:
        SharedStorage.for_build(workspace(game), "jenkins-42")

    assert error.value.section == "Jenkins"


def test_preparing_a_single_node_clears_its_subfolder_and_the_ci_folders(game: Path, tmp_path: Path) -> None:
    build = tmp_path / "Storage" / "tag"
    (build / "Task").mkdir(parents=True)
    (build / "Other Task").mkdir()
    for folder in ["Jenkins", "Tests"]:
        (game / "Saved" / folder).mkdir(parents=True)

    SharedStorage.for_build(workspace(game), "tag").prepare_single_node("Task")

    assert not (build / "Task").exists()
    assert (build / "Other Task").exists()
    assert not (game / "Saved" / "Jenkins").exists()
    assert not (game / "Saved" / "Tests").exists()
    assert (game / "Saved" / "BuildGraph" / "CITaskVersionFile.txt").read_text() == "tag"


def test_preparing_a_single_node_keeps_the_local_buildgraph_folder_for_the_same_build_tag(game: Path) -> None:
    local = game / "Saved" / "BuildGraph"
    local.mkdir(parents=True)
    (local / "CITaskVersionFile.txt").write_text("tag")
    (local / "Cached.txt").write_text("keep me")

    SharedStorage.for_build(workspace(game), "tag").prepare_single_node("Task")

    assert (local / "Cached.txt").exists()


def test_preparing_a_single_node_resets_the_local_buildgraph_folder_for_a_new_build_tag(game: Path) -> None:
    local = game / "Saved" / "BuildGraph"
    local.mkdir(parents=True)
    (local / "CITaskVersionFile.txt").write_text("old-tag")
    (local / "Cached.txt").write_text("stale")

    SharedStorage.for_build(workspace(game), "new-tag").prepare_single_node("Task")

    assert not (local / "Cached.txt").exists()
    assert (local / "CITaskVersionFile.txt").read_text() == "new-tag"


def test_a_subfolder_that_cannot_be_removed_stops_the_preparation(game: Path, tmp_path: Path) -> None:
    build = tmp_path / "Storage" / "tag"
    build.mkdir(parents=True)
    (build / "Task").write_text("a file where the Single node's folder should be")

    with pytest.raises(OSError):
        SharedStorage.for_build(workspace(game), "tag").prepare_single_node("Task")


def test_delete_removes_the_build_folder_and_leaves_other_builds_alone(game: Path, tmp_path: Path) -> None:
    (tmp_path / "Storage" / "tag" / "Task").mkdir(parents=True)
    (tmp_path / "Storage" / "other-tag").mkdir()

    SharedStorage.for_build(workspace(game), "tag").delete()

    assert not (tmp_path / "Storage" / "tag").exists()
    assert (tmp_path / "Storage" / "other-tag").exists()


def test_deleting_a_missing_build_folder_does_nothing(game: Path, tmp_path: Path) -> None:
    SharedStorage.for_build(workspace(game), "never-ran").delete()

    assert not (tmp_path / "Storage" / "never-ran").exists()


def test_a_delete_that_fails_raises(game: Path, tmp_path: Path) -> None:
    (tmp_path / "Storage").mkdir()
    (tmp_path / "Storage" / "tag").write_text("a file where the build's folder should be")

    with pytest.raises(OSError):
        SharedStorage.for_build(workspace(game), "tag").delete()


def test_ci_cleanup_deletes_the_shared_storage_of_its_build_tag(game: Path, tmp_path: Path) -> None:
    (tmp_path / "Storage" / "jenkins-42" / "Task").mkdir(parents=True)

    ci_cleanup.main(["--build_tag=jenkins-42", f"--uproject-path={game / 'Game.uproject'}"])

    assert not (tmp_path / "Storage" / "jenkins-42").exists()
