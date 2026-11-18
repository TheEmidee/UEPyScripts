from pathlib import Path

import pytest

from uepyscripts.internal.buildgraph import BuildGraphError
from uepyscripts.internal.workspace import Workspace
from uepyscripts.tools.ci.single_node import single_node_command


def workspace(game: Path) -> Workspace:
    return Workspace(game / "Game.uproject")


def test_the_command_runs_the_node_with_the_shared_storage_of_its_build_on_a_build_machine(game: Path, tmp_path: Path) -> None:
    command = single_node_command(workspace(game), "Compile Win64", "jenkins-42", extra_args=["-set:Clean=True"])

    assert command.uat_arguments() == [
        "BuildGraph",
        f"-script={(game / 'Build' / 'Graph.xml').resolve()}",
        "-SingleNode=Compile Win64",
        f"-Project={(game / 'Game.uproject').resolve()}",
        "-BuildMachine",
        "-NoP4",
        f"-SharedStorageDir={tmp_path / 'Storage' / 'jenkins-42'}",
        "-WriteToSharedStorage",
        "-set:Clean=True",
    ]


@pytest.mark.parametrize("script_name", ["Missing.xml", "Graph.txt"])
def test_a_bad_script_leaves_the_shared_storage_and_this_machine_untouched(game: Path, tmp_path: Path, script_name: str) -> None:
    script = game / script_name
    if script_name.endswith(".txt"):
        script.write_text("")
    node_folder = tmp_path / "Storage" / "tag" / "Task"
    node_folder.mkdir(parents=True)
    local = game / "Saved" / "BuildGraph"
    local.mkdir(parents=True)
    (local / "CITaskVersionFile.txt").write_text("old-tag")
    for folder in ["Jenkins", "Tests"]:
        (game / "Saved" / folder).mkdir(parents=True)

    with pytest.raises(BuildGraphError):
        single_node_command(workspace(game), "Task", "tag", script=script)

    assert node_folder.exists()
    assert (local / "CITaskVersionFile.txt").read_text() == "old-tag"
    assert (game / "Saved" / "Jenkins").exists()
    assert (game / "Saved" / "Tests").exists()


def test_the_node_subfolder_and_the_ci_folders_are_cleared(game: Path, tmp_path: Path) -> None:
    build = tmp_path / "Storage" / "tag"
    (build / "Task").mkdir(parents=True)
    (build / "Other Task").mkdir()
    for folder in ["Jenkins", "Tests"]:
        (game / "Saved" / folder).mkdir(parents=True)

    single_node_command(workspace(game), "Task", "tag")

    assert not (build / "Task").exists()
    assert (build / "Other Task").exists()
    assert not (game / "Saved" / "Jenkins").exists()
    assert not (game / "Saved" / "Tests").exists()
    assert (game / "Saved" / "BuildGraph" / "CITaskVersionFile.txt").read_text() == "tag"


def test_the_local_buildgraph_folder_is_kept_for_the_same_build_tag(game: Path) -> None:
    local = game / "Saved" / "BuildGraph"
    local.mkdir(parents=True)
    (local / "CITaskVersionFile.txt").write_text("tag")
    (local / "Cached.txt").write_text("keep me")

    single_node_command(workspace(game), "Task", "tag")

    assert (local / "Cached.txt").exists()


def test_the_local_buildgraph_folder_is_reset_for_a_new_build_tag(game: Path) -> None:
    local = game / "Saved" / "BuildGraph"
    local.mkdir(parents=True)
    (local / "CITaskVersionFile.txt").write_text("old-tag")
    (local / "Cached.txt").write_text("stale")

    single_node_command(workspace(game), "Task", "new-tag")

    assert not (local / "Cached.txt").exists()
    assert (local / "CITaskVersionFile.txt").read_text() == "new-tag"


def test_a_node_subfolder_that_cannot_be_removed_stops_the_preparation(game: Path, tmp_path: Path) -> None:
    build = tmp_path / "Storage" / "tag"
    build.mkdir(parents=True)
    (build / "Task").write_text("a file where the Single node's folder should be")

    with pytest.raises(OSError):
        single_node_command(workspace(game), "Task", "tag")
