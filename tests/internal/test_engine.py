import json
import sys
from pathlib import Path

import pytest

from uepyscripts.internal.engine import Engine
from uepyscripts.internal.errors import WorkspaceError
from uepyscripts.internal.process import EngineToolNotStartedError, PopenRunner
from uepyscripts.internal.project import Project


class RecordingRunner:
    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.ran: list[list[str]] = []
        self.started: list[list[str]] = []

    def run(self, argv: list[str]) -> int:
        self.ran.append(argv)
        return self.exit_code

    def start(self, argv: list[str]) -> None:
        self.started.append(argv)


@pytest.fixture
def engine_root(tmp_path: Path) -> Path:
    """A freshly cloned engine: Build.version only, no Engine tool built yet."""
    build = tmp_path / "Engine" / "Build"
    build.mkdir(parents=True)
    (build / "Build.version").write_text(json.dumps({"MajorVersion": 5, "MinorVersion": 4, "PatchVersion": 2}))
    return tmp_path


@pytest.fixture
def project(engine_root: Path) -> Project:
    folder = engine_root / "Game"
    folder.mkdir()
    uproject = folder / "Game.uproject"
    uproject.write_text(json.dumps({"EngineAssociation": ""}))
    return Project(uproject)


def make_engine(project: Project, engine_root: Path, runner: RecordingRunner) -> Engine:
    return Engine(project, engine_root, runner)


def tool(engine_root: Path, *parts: str) -> str:
    return str((engine_root / "Engine").resolve().joinpath(*parts))


def test_engine_builds_without_any_engine_tool(project: Project, engine_root: Path) -> None:
    engine = make_engine(project, engine_root, RecordingRunner())

    assert str(engine.version) == "5.4.2"
    assert engine.root_path == engine_root


def test_compile_editor_runs_build_bat_on_the_editor_target(project: Project, engine_root: Path) -> None:
    runner = RecordingRunner()

    make_engine(project, engine_root, runner).compile_editor()

    assert runner.ran == [
        [
            tool(engine_root, "Build", "BatchFiles", "Build.bat"),
            "GameEditor",
            "Win64",
            "Development",
            f"-project={project.uproject_path}",
            "-WaitMutex",
            "-FromMsBuild",
            f"-log={project.root_folder}/Saved/Logs/Compile_Editor_Development_Win64.log",
        ]
    ]


def test_generate_project_files_goes_through_build_bat_with_the_project_once(project: Project, engine_root: Path) -> None:
    runner = RecordingRunner()

    make_engine(project, engine_root, runner).generate_project_files()

    [argv] = runner.ran
    assert argv == [
        tool(engine_root, "Build", "BatchFiles", "Build.bat"),
        "-projectfiles",
        f"-project={project.uproject_path}",
        "-game",
        "-rocket",
        "-progress",
    ]
    assert sum(str(project.uproject_path) in arg for arg in argv) == 1


def test_raw_ubt_prepends_the_uproject(project: Project, engine_root: Path) -> None:
    runner = RecordingRunner()

    make_engine(project, engine_root, runner).ubt(["-mode=QueryTargets"])

    assert runner.ran == [
        [tool(engine_root, "Binaries", "DotNET", "UnrealBuildTool", "UnrealBuildTool.exe"), str(project.uproject_path), "-mode=QueryTargets"]
    ]


def test_raw_uat_forwards_its_arguments_unchanged(project: Project, engine_root: Path) -> None:
    runner = RecordingRunner()

    make_engine(project, engine_root, runner).uat(["turnkey", "-command=VerifySdk"])

    assert runner.ran == [[tool(engine_root, "Build", "BatchFiles", "RunUAT.bat"), "turnkey", "-command=VerifySdk"]]


def test_launch_editor_starts_in_the_background(project: Project, engine_root: Path) -> None:
    runner = RecordingRunner()

    make_engine(project, engine_root, runner).launch_editor()

    assert runner.ran == []
    assert runner.started == [[tool(engine_root, "Binaries", "Win64", "UnrealEditor.exe"), str(project.uproject_path)]]


def test_exit_codes_pass_through(project: Project, engine_root: Path) -> None:
    engine = make_engine(project, engine_root, RecordingRunner(exit_code=6))

    assert engine.uat([]) == 6
    assert engine.ubt([]) == 6
    assert engine.compile_editor() == 6
    assert engine.generate_project_files() == 6


def test_popen_runner_reports_a_tool_that_cannot_be_started(tmp_path: Path) -> None:
    missing = str(tmp_path / "Engine" / "Binaries" / "DotNET" / "UnrealBuildTool" / "UnrealBuildTool.exe")

    with pytest.raises(EngineToolNotStartedError) as error:
        PopenRunner().run([missing, "-help"])

    assert error.value.executable == missing
    assert isinstance(error.value, WorkspaceError)

    with pytest.raises(EngineToolNotStartedError):
        PopenRunner().start([missing])


def test_popen_runner_returns_the_exit_code(tmp_path: Path) -> None:
    code = PopenRunner().run([sys.executable, "-c", "import sys; print('hello'); sys.exit(3)"])

    assert code == 3
