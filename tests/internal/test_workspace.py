import argparse
import json
from pathlib import Path

import pytest

from uepyscripts.internal.workspace import (
    EngineNotFoundError,
    ProjectNotFoundError,
    Workspace,
    add_uproject_argument,
    open_workspace,
)


def write_build_version(root: Path) -> None:
    build_folder = root / "Engine" / "Build"
    build_folder.mkdir(parents=True, exist_ok=True)
    (build_folder / "Build.version").write_text(json.dumps({"MajorVersion": 5, "MinorVersion": 4, "PatchVersion": 2}))


def write_uproject(folder: Path, engine_association: str = "") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    uproject = folder / f"{folder.name}.uproject"
    uproject.write_text(json.dumps({"EngineAssociation": engine_association}))
    return uproject


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

    with pytest.raises(EngineNotFoundError):
        _ = workspace.engine

    write_build_version(tmp_path)

    assert workspace.engine.root_path == tmp_path


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


def test_open_workspace_exits_on_missing_engine_inside_the_block(tmp_path: Path) -> None:
    args, _ = uproject_args("--uproject-path", str(write_uproject(tmp_path / "Game")))

    with pytest.raises(SystemExit) as exit_info:
        with open_workspace(args) as workspace:
            _ = workspace.engine

    assert exit_info.value.code == 1


def test_open_workspace_lets_other_errors_through(native_layout: Path) -> None:
    args, _ = uproject_args("--uproject-path", str(native_layout))

    with pytest.raises(RuntimeError):
        with open_workspace(args):
            raise RuntimeError("not a WorkspaceError")
