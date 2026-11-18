import argparse
import json
from pathlib import Path

import pytest

from tests.fakes import DictRegistry, RecordingRunner, tool, write_build_version, write_uproject
from uepyscripts.internal.engine_locator import REGISTERED_BUILDS_KEY, EngineLocator
from uepyscripts.internal.workspace import (
    EngineNotFoundError,
    InvalidEngineError,
    InvalidProjectError,
    ProjectNotFoundError,
    Workspace,
    WorkspaceError,
    add_uproject_argument,
    open_workspace,
)


@pytest.fixture
def native_layout(tmp_path: Path) -> Path:
    """A Native project: the engine tree's root holds both Engine/ and Game/."""
    write_build_version(tmp_path)
    uproject = write_uproject(tmp_path / "Game")
    config_folder = tmp_path / "Game" / "Config" / "PyScripts"
    config_folder.mkdir(parents=True)
    (config_folder / "config.ini").write_text("[Jenkins]\nBuildgraphSharedStoragePath = \\\\nas\\storage\n")
    return uproject


def uproject_args(*argv: str) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    add_uproject_argument(parser)
    return parser.parse_known_args(list(argv))


def test_found_from_explicit_uproject_path(native_layout: Path) -> None:
    workspace = Workspace(native_layout)

    assert workspace.project.uproject_path == native_layout.resolve()
    assert workspace.project.project_name == "Game"


def test_found_by_searching_up_from_a_subfolder(native_layout: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    subfolder = native_layout.parent / "Source" / "Game"
    subfolder.mkdir(parents=True)
    monkeypatch.chdir(subfolder)

    workspace = Workspace()

    assert workspace.project.uproject_path == native_layout.resolve()


def test_missing_uproject_raises_project_not_found(tmp_path: Path) -> None:
    with pytest.raises(ProjectNotFoundError):
        Workspace(tmp_path / "Missing" / "Missing.uproject")


def test_no_uproject_above_the_current_folder_raises_project_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ProjectNotFoundError):
        Workspace()


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("{ not json", id="not json"),
        pytest.param(json.dumps({"FileVersion": 3}), id="no EngineAssociation"),
        pytest.param(json.dumps({"EngineAssociation": 5.4}), id="EngineAssociation not a string"),
        pytest.param(json.dumps(["EngineAssociation"]), id="not an object"),
    ],
)
def test_a_malformed_uproject_raises_invalid_project(tmp_path: Path, content: str) -> None:
    uproject = write_uproject(tmp_path / "Game")
    uproject.write_text(content)

    with pytest.raises(InvalidProjectError) as error:
        Workspace(uproject)

    assert str(uproject.resolve()) in str(error.value)
    assert isinstance(error.value, WorkspaceError)


def test_config_is_readable_without_an_engine(tmp_path: Path) -> None:
    uproject = write_uproject(tmp_path / "Game")
    config_folder = tmp_path / "Game" / "Config" / "PyScripts"
    config_folder.mkdir(parents=True)
    (config_folder / "config.ini").write_text("[Jenkins]\nBuildgraphSharedStoragePath = X\n")

    workspace = Workspace(uproject)

    assert workspace.config.jenkins.buildgraph_shared_storage_path == Path("X")


def test_engine_is_resolved_lazily_and_cached(native_layout: Path) -> None:
    workspace = Workspace(native_layout)
    build_version = native_layout.parent.parent / "Engine" / "Build" / "Build.version"

    engine = workspace.engine
    build_version.unlink()

    assert str(engine.version) == "5.4.2"
    assert workspace.engine is engine


def test_missing_engine_raises_then_a_later_access_succeeds(tmp_path: Path) -> None:
    uproject = write_uproject(tmp_path / "Game")
    workspace = Workspace(uproject)

    with pytest.raises(EngineNotFoundError) as error:
        _ = workspace.engine

    assert "Build.version" in str(error.value)

    write_build_version(tmp_path)

    assert workspace.engine.root_path == tmp_path


def test_an_engine_no_step_locates_raises_engine_not_found(tmp_path: Path) -> None:
    uproject = write_uproject(tmp_path / "Game", engine_association="MyBuild")
    workspace = Workspace(uproject, locator=EngineLocator(DictRegistry(), {}))

    with pytest.raises(EngineNotFoundError):
        _ = workspace.engine


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("{ not json", id="not json"),
        pytest.param(json.dumps({"MajorVersion": 5, "MinorVersion": 4}), id="no PatchVersion"),
        pytest.param(json.dumps({"MajorVersion": 5, "MinorVersion": 4, "PatchVersion": "two"}), id="not a number"),
        pytest.param(json.dumps([5, 4, 2]), id="not an object"),
    ],
)
def test_a_malformed_build_version_raises_invalid_engine(tmp_path: Path, content: str) -> None:
    build_version = write_build_version(tmp_path, content)
    workspace = Workspace(write_uproject(tmp_path / "Game"))

    with pytest.raises(InvalidEngineError) as error:
        _ = workspace.engine

    assert str(build_version.resolve()) in str(error.value)


def test_a_malformed_jenkins_build_version_raises_invalid_engine(tmp_path: Path) -> None:
    build_version = write_build_version(tmp_path)
    jenkins_version = build_version.with_name("JenkinsBuild.version")
    jenkins_version.write_text("not a version")
    workspace = Workspace(write_uproject(tmp_path / "Game"))

    with pytest.raises(InvalidEngineError) as error:
        _ = workspace.engine

    assert str(jenkins_version.resolve()) in str(error.value)


def test_the_jenkins_build_number_is_appended_to_the_version(native_layout: Path) -> None:
    build_version = native_layout.parent.parent / "Engine" / "Build" / "Build.version"
    build_version.with_name("JenkinsBuild.version").write_text("42\n")

    assert str(Workspace(native_layout).engine.version) == "5.4.2.42"


def test_the_engine_is_located_through_the_given_locator(tmp_path: Path) -> None:
    engine_root = tmp_path / "Engines" / "MyBuild"
    write_build_version(engine_root)
    registry = DictRegistry({("HKCU", REGISTERED_BUILDS_KEY, "MyBuild"): str(engine_root)})
    uproject = write_uproject(tmp_path / "Game", engine_association="MyBuild")

    workspace = Workspace(uproject, locator=EngineLocator(registry, {}))

    assert workspace.engine.root_path == engine_root


def test_engine_tools_launch_through_the_given_runner(native_layout: Path, tmp_path: Path) -> None:
    runner = RecordingRunner(exit_code=3)
    workspace = Workspace(native_layout, runner=runner)

    assert workspace.engine.uat(["BuildCookRun"]) == 3
    assert runner.ran == [[tool(tmp_path, "Build", "BatchFiles", "RunUAT.bat"), "BuildCookRun"]]


def test_native_layout_is_detected_as_native(native_layout: Path, tmp_path: Path) -> None:
    foreign = write_uproject(tmp_path / "Other" / "Foreign", engine_association="5.4")

    assert Workspace(native_layout).project.is_native_project
    assert not Workspace(foreign).project.is_native_project


def test_uproject_path_is_consumed_and_other_arguments_forwarded(native_layout: Path) -> None:
    args, forwarded = uproject_args("turnkey", "--uproject-path", str(native_layout), "-command=VerifySdk", "-platform=Win64")

    assert args.uproject_path == native_layout
    assert forwarded == ["turnkey", "-command=VerifySdk", "-platform=Win64"]


def test_open_workspace_exits_on_missing_project(tmp_path: Path) -> None:
    args, _ = uproject_args("--uproject-path", str(tmp_path / "Missing.uproject"))

    with pytest.raises(SystemExit) as exit_info:
        with open_workspace(args):
            pass

    assert exit_info.value.code == 1


def test_open_workspace_exits_on_a_malformed_project(tmp_path: Path) -> None:
    uproject = write_uproject(tmp_path / "Game")
    uproject.write_text("{ not json")
    args, _ = uproject_args("--uproject-path", str(uproject))

    with pytest.raises(SystemExit) as exit_info:
        with open_workspace(args):
            pass

    assert exit_info.value.code == 1


def test_open_workspace_exits_on_missing_engine_inside_the_block(tmp_path: Path) -> None:
    args, _ = uproject_args("--uproject-path", str(write_uproject(tmp_path / "Game")))

    with pytest.raises(SystemExit) as exit_info:
        with open_workspace(args) as workspace:
            _ = workspace.engine

    assert exit_info.value.code == 1


def test_open_workspace_launches_engine_tools_through_the_given_runner(native_layout: Path) -> None:
    runner = RecordingRunner()
    args, _ = uproject_args("--uproject-path", str(native_layout))

    with open_workspace(args, runner=runner) as workspace:
        workspace.engine.launch_editor()

    assert len(runner.started) == 1


def test_open_workspace_lets_other_errors_through(native_layout: Path) -> None:
    args, _ = uproject_args("--uproject-path", str(native_layout))

    with pytest.raises(RuntimeError):
        with open_workspace(args):
            raise RuntimeError("not a WorkspaceError")
