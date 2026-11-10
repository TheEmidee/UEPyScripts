import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from uepyscripts.internal.workspace import Workspace
from uepyscripts.tools.ci import buildgraph as ci_buildgraph


class RecordingEngine:
    def __init__(self) -> None:
        self.uat_calls: list[list[str]] = []

    def uat(self, args: list[str]) -> int:
        self.uat_calls.append(args)
        return 0


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
