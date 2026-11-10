import argparse
import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from uepyscripts.internal.project import Project
from uepyscripts.internal.workspace import Workspace
from uepyscripts.tools.ci import buildgraph as ci_buildgraph
from uepyscripts.tools.ci.buildgraph import prepare_ci_folders


class RecordingEngine:
    def __init__(self) -> None:
        self.uat_calls: list[list[str]] = []

    def uat(self, args: list[str]) -> int:
        self.uat_calls.append(args)
        return 0


@pytest.fixture
def game(tmp_path: Path) -> Path:
    game = tmp_path / "Game"
    (game / "Build").mkdir(parents=True)
    (game / "Build" / "Graph.xml").write_text("<BuildGraph/>")
    (game / "Game.uproject").write_text(json.dumps({"EngineAssociation": ""}))
    config = game / "Config" / "PyScripts"
    config.mkdir(parents=True)
    (config / "config.ini").write_text(
        f"[Project]\nBuildgraphPath = Build/Graph.xml\n[Jenkins]\nBuildgraphSharedStoragePath = {tmp_path / 'Storage'}\n"
    )
    return game


def run_ci(game: Path, argv: list[str], monkeypatch: pytest.MonkeyPatch) -> RecordingEngine:
    engine = RecordingEngine()

    @contextmanager
    def fake_open_workspace(args: argparse.Namespace) -> Iterator[SimpleNamespace]:
        workspace = Workspace(game / "Game.uproject")
        yield SimpleNamespace(project=workspace.project, config=workspace.config, engine=engine)

    monkeypatch.setattr(ci_buildgraph, "open_workspace", fake_open_workspace)
    ci_buildgraph.main(argv)
    return engine


def test_single_node_runs_with_shared_storage(game: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = run_ci(game, ["--target=Compile Win64", "--build_tag=jenkins-42", "-set:Clean=True", "-NoP4"], monkeypatch)

    storage = tmp_path / "Storage" / "jenkins-42"
    assert engine.uat_calls == [
        [
            "BuildGraph",
            f"-script={(game / 'Build' / 'Graph.xml').resolve()}",
            "-SingleNode=Compile Win64",
            f"-Project={(game / 'Game.uproject').resolve()}",
            "-set:Clean=True",
            "-BuildMachine",
            f"-SharedStorageDir={storage}",
            "-WriteToSharedStorage",
            "-NoP4",
        ]
    ]


def test_no_single_node_runs_the_target_without_shared_storage(game: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    engine = run_ci(game, ["--target=Compile Win64", "--build_tag=jenkins-42", "--no-single-node"], monkeypatch)

    assert engine.uat_calls == [
        [
            "BuildGraph",
            f"-script={(game / 'Build' / 'Graph.xml').resolve()}",
            "-target=Compile Win64",
            f"-Project={(game / 'Game.uproject').resolve()}",
            "-BuildMachine",
            "-NoP4",
        ]
    ]
    assert not (game / "Saved").exists()


def test_explicit_script_is_used(game: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    other = tmp_path / "Other.xml"
    other.write_text("<BuildGraph/>")

    engine = run_ci(game, ["--target=T", "--build_tag=b", "--no-single-node", f"--script={other}"], monkeypatch)

    assert engine.uat_calls[0][1] == f"-script={other}"


def make_project(game: Path) -> Project:
    return Project(game / "Game.uproject")


def test_prepare_ci_folders_clears_the_task_storage_and_ci_folders(game: Path, tmp_path: Path) -> None:
    storage = tmp_path / "Storage" / "tag"
    (storage / "Task").mkdir(parents=True)
    (storage / "Other Task").mkdir()
    for folder in ["Jenkins", "Tests"]:
        (game / "Saved" / folder).mkdir(parents=True)

    prepare_ci_folders(make_project(game), storage, "tag", "Task")

    assert not (storage / "Task").exists()
    assert (storage / "Other Task").exists()
    assert not (game / "Saved" / "Jenkins").exists()
    assert not (game / "Saved" / "Tests").exists()
    assert (game / "Saved" / "BuildGraph" / "CITaskVersionFile.txt").read_text() == "tag"


def test_prepare_ci_folders_keeps_the_local_buildgraph_folder_for_the_same_tag(game: Path, tmp_path: Path) -> None:
    local = game / "Saved" / "BuildGraph"
    local.mkdir(parents=True)
    (local / "CITaskVersionFile.txt").write_text("tag")
    (local / "Cached.txt").write_text("keep me")

    prepare_ci_folders(make_project(game), tmp_path / "Storage" / "tag", "tag", "Task")

    assert (local / "Cached.txt").exists()


def test_prepare_ci_folders_clears_the_local_buildgraph_folder_for_a_new_tag(game: Path, tmp_path: Path) -> None:
    local = game / "Saved" / "BuildGraph"
    local.mkdir(parents=True)
    (local / "CITaskVersionFile.txt").write_text("old-tag")
    (local / "Cached.txt").write_text("stale")

    prepare_ci_folders(make_project(game), tmp_path / "Storage" / "new-tag", "new-tag", "Task")

    assert not (local / "Cached.txt").exists()
    assert (local / "CITaskVersionFile.txt").read_text() == "new-tag"
