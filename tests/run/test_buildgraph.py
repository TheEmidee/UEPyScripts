from pathlib import Path

from tests.fakes import RecordingRunner, tool, write_build_version, write_uproject
from uepyscripts.run import buildgraph


def test_the_target_runs_through_uat_with_the_extra_arguments(tmp_path: Path) -> None:
    write_build_version(tmp_path)
    uproject = write_uproject(tmp_path / "Game")
    script = tmp_path / "Game" / "Graph.xml"
    script.write_text("<BuildGraph/>")
    runner = RecordingRunner(exit_code=4)

    exit_code = buildgraph.main(["--target=Compile Win64", f"--script={script}", f"--uproject-path={uproject}", "-set:Clean=True"], runner=runner)

    assert exit_code == 4
    assert runner.ran == [
        [
            tool(tmp_path, "Build", "BatchFiles", "RunUAT.bat"),
            "BuildGraph",
            f"-script={script}",
            "-target=Compile Win64",
            f"-Project={uproject.resolve()}",
            "-set:Clean=True",
        ]
    ]
