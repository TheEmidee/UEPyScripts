import json
from pathlib import Path
from typing import Optional

import pytest

from uepyscripts.internal.engine_locator import (
    LAUNCHER_INSTALL_KEY,
    REGISTERED_BUILDS_KEY,
    EngineLocator,
    Hive,
)
from uepyscripts.internal.project import Project


class DictRegistry:
    def __init__(self, values: Optional[dict[tuple[Hive, str, str], str]] = None) -> None:
        self.values = values or {}
        self.reads: list[tuple[Hive, str, str]] = []

    def read(self, hive: Hive, key: str, name: str) -> Optional[str]:
        self.reads.append((hive, key, name))
        return self.values.get((hive, key, name))


def make_project(folder: Path, engine_association: str) -> Project:
    folder.mkdir(parents=True, exist_ok=True)
    uproject = folder / f"{folder.name}.uproject"
    uproject.write_text(json.dumps({"EngineAssociation": engine_association}))
    return Project(uproject)


def make_folder(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_launcher_manifest(program_data: Path, installations: list[dict[str, str]]) -> None:
    manifest = program_data / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"InstallationList": installations}))


def test_native_project_engine_is_the_parent_folder(tmp_path: Path) -> None:
    project = make_project(tmp_path / "Game", "")

    assert EngineLocator(DictRegistry(), {}).locate(project) == tmp_path


def test_registered_build_wins_over_the_env_var(tmp_path: Path) -> None:
    registered = make_folder(tmp_path / "Registered")
    make_folder(tmp_path / "EnvRoot" / "MyEngine")
    project = make_project(tmp_path / "Game", "MyEngine")
    registry = DictRegistry({("HKCU", REGISTERED_BUILDS_KEY, "MyEngine"): str(registered)})

    located = EngineLocator(registry, {"NODE_UE_ROOT": str(tmp_path / "EnvRoot")}).locate(project)

    assert located == registered


def test_launcher_install_found_in_the_registry(tmp_path: Path) -> None:
    install = make_folder(tmp_path / "UE_5.4")
    project = make_project(tmp_path / "Game", "5.4")
    registry = DictRegistry({("HKLM", rf"{LAUNCHER_INSTALL_KEY}\5.4", "InstalledDirectory"): str(install)})

    assert EngineLocator(registry, {}).locate(project) == install


def test_launcher_install_found_in_the_launcher_manifest(tmp_path: Path) -> None:
    install = make_folder(tmp_path / "UE_5.3")
    write_launcher_manifest(
        tmp_path / "ProgramData",
        [
            {"InstallLocation": str(tmp_path / "Fortnite"), "AppName": "Fortnite", "AppVersion": "5.3"},
            {"InstallLocation": str(install), "AppName": "UE_5.3", "AppVersion": "5.3.2-29314046+++UE5+Release-5.3"},
        ],
    )
    project = make_project(tmp_path / "Game", "5.3")

    located = EngineLocator(DictRegistry(), {"PROGRAMDATA": str(tmp_path / "ProgramData")}).locate(project)

    assert located == install


def test_unreadable_launcher_manifest_falls_through_to_the_env_var(tmp_path: Path) -> None:
    manifest = tmp_path / "ProgramData" / "Epic" / "UnrealEngineLauncher" / "LauncherInstalled.dat"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("not json")
    engine = make_folder(tmp_path / "EnvRoot" / "5.4")
    project = make_project(tmp_path / "Game", "5.4")

    environ = {"PROGRAMDATA": str(tmp_path / "ProgramData"), "NODE_UE_ROOT": str(tmp_path / "EnvRoot")}

    assert EngineLocator(DictRegistry(), environ).locate(project) == engine


def test_custom_build_never_asks_the_launcher_registry(tmp_path: Path) -> None:
    make_folder(tmp_path / "EnvRoot" / "MyEngine")
    project = make_project(tmp_path / "Game", "MyEngine")
    registry = DictRegistry()

    EngineLocator(registry, {"NODE_UE_ROOT": str(tmp_path / "EnvRoot")}).locate(project)

    assert [hive for hive, _, _ in registry.reads] == ["HKCU"]


def test_engine_association_as_a_relative_path(tmp_path: Path) -> None:
    engine = make_folder(tmp_path / "Engines" / "Custom")
    project = make_project(tmp_path / "Projects" / "Game", "../../Engines/Custom")

    assert EngineLocator(DictRegistry(), {}).locate(project) == engine.resolve()


def test_engine_association_as_an_absolute_path(tmp_path: Path) -> None:
    engine = make_folder(tmp_path / "Engines" / "Custom")
    project = make_project(tmp_path / "Game", str(engine))

    assert EngineLocator(DictRegistry(), {}).locate(project) == engine


def test_engine_association_path_to_nothing_lets_the_env_var_answer(tmp_path: Path) -> None:
    project = make_project(tmp_path / "Game", "MissingEngine")
    engine = make_folder(tmp_path / "EnvRoot" / "MissingEngine")

    assert EngineLocator(DictRegistry(), {"NODE_UE_ROOT": str(tmp_path / "EnvRoot")}).locate(project) == engine


def test_nothing_found_raises(tmp_path: Path) -> None:
    project = make_project(tmp_path / "Game", "MyEngine")

    with pytest.raises(FileNotFoundError):
        EngineLocator(DictRegistry(), {}).locate(project)


def test_env_var_pointing_at_nothing_raises(tmp_path: Path) -> None:
    project = make_project(tmp_path / "Game", "MyEngine")

    with pytest.raises(FileNotFoundError):
        EngineLocator(DictRegistry(), {"NODE_UE_ROOT": str(tmp_path / "Nowhere")}).locate(project)
