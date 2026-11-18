from pathlib import Path

from tests.fakes import RecordingRunner, tool
from uepyscripts.tools.ci import buildgraph as ci_buildgraph


def run_ci(game: Path, argv: list[str]) -> list[list[str]]:
    """Runs ue-ci-run-buildgraph on the `game` project. Returns the arguments of every UAT run."""
    runner = RecordingRunner()
    ci_buildgraph.main([*argv, f"--uproject-path={game / 'Game.uproject'}"], runner=runner)

    uat = tool(game.parent, "Build", "BatchFiles", "RunUAT.bat")
    assert all(call[0] == uat for call in runner.ran)
    return [call[1:] for call in runner.ran]


def test_single_node_runs_with_shared_storage(game: Path, tmp_path: Path) -> None:
    uat_calls = run_ci(game, ["--target=Compile Win64", "--build_tag=jenkins-42", "-set:Clean=True", "-NoP4"])

    storage = tmp_path / "Storage" / "jenkins-42"
    assert uat_calls == [
        [
            "BuildGraph",
            f"-script={(game / 'Build' / 'Graph.xml').resolve()}",
            "-SingleNode=Compile Win64",
            f"-Project={(game / 'Game.uproject').resolve()}",
            "-BuildMachine",
            f"-SharedStorageDir={storage}",
            "-WriteToSharedStorage",
            "-set:Clean=True",
            "-NoP4",
        ]
    ]


def test_no_single_node_runs_the_target_without_shared_storage(game: Path) -> None:
    uat_calls = run_ci(game, ["--target=Compile Win64", "--build_tag=jenkins-42", "--no-single-node"])

    assert uat_calls == [
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


def test_explicit_script_is_used(game: Path, tmp_path: Path) -> None:
    other = tmp_path / "Other.xml"
    other.write_text("<BuildGraph/>")

    uat_calls = run_ci(game, ["--target=T", "--build_tag=b", "--no-single-node", f"--script={other}"])

    assert uat_calls[0][1] == f"-script={other}"
