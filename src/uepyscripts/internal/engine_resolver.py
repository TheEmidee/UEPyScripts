import os
import winreg
from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from .. import logger
from ..internal.project import Project
from ..tools.helpers import get_engine_root_folder_from_env_var, is_engine_from_egs
from ..tools.winreg import get_registry_value


def resolve_engine_from_env_var(project: Project) -> Optional[Path]:
    return get_engine_root_folder_from_env_var(project.engine_association)


def resolve_engine_from_registry(project: Project) -> Optional[Path]:
    path = get_registry_value(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Epic Games\Unreal Engine\Builds", project.engine_association)
    if path:
        return Path(path)

    return None


def resolve_engine_from_egs(project: Project) -> Optional[Path]:
    if is_engine_from_egs(project.engine_association):
        registry_value = get_registry_value(
            winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\EpicGames\Unreal Engine\{project.engine_association}", "InstalledDirectory"
        )
        if registry_value:
            return Path(registry_value)

    # Some installations are listed in LauncherInstalled.dat
    class EpicInstallation(BaseModel):
        InstallLocation: str
        AppName: str
        AppVersion: str

        @property
        def is_engine(self) -> bool:
            """Checks if the installation is an Unreal Engine build."""
            return self.AppName.startswith("UE_")

    class LauncherInstalledData(BaseModel):
        InstallationList: list[EpicInstallation]

    def get_dat_file_path() -> Path:
        # os.path.expandvars automatically replaces %PROGRAMDATA% with the actual path
        raw_path = r"%PROGRAMDATA%\Epic\UnrealEngineLauncher\LauncherInstalled.dat"
        expanded_path = Path(os.path.expandvars(raw_path))

        return expanded_path

    dat_path = get_dat_file_path()
    if not dat_path.exists():
        return None

    try:
        with open(dat_path, "r", encoding="utf-8") as f:
            json_str = f.read()
            data = LauncherInstalledData.model_validate_json(json_str)

            for item in data.InstallationList:
                if item.is_engine and item.AppVersion.startswith(project.engine_association):
                    return Path(item.InstallLocation)

    except Exception as e:
        logger.error(f"Error parsing manifest: {e}")

    return None


def resolve_engine_from_path(project: Project) -> Optional[Path]:
    path = Path(project.engine_association)
    if not os.path.isabs(path):
        path = (project.root_folder / path).resolve()

    # Check path exists otherwise we could return a semantically valid path to a folder which does not exist
    # and that would make the resolve fail without trying resolvers which are further down in the list
    if os.path.isabs(path) and path.exists():
        return path

    return None


def resolve_engine_path(project: Project) -> Path:
    resolvers = [
        resolve_engine_from_registry,
        resolve_engine_from_egs,
        resolve_engine_from_path,
        # Resolve last with the environment variable to avoid failing the resolution on a machine
        # where there's the environment variable but the engine is installed using the launcher
        resolve_engine_from_env_var,
    ]

    for resolver in resolvers:
        path = resolver(project)
        if path:
            logger.info(f"Engine path resolved via '{resolver.__name__}': {path}")
            break
    else:
        raise FileNotFoundError("Impossible to locate the engine")

    path_str = str(path).strip()
    # Check that the path exists and is not a degenerate path containing only . or \\
    if not (path.exists() and path_str not in ["", ".", "\\"]):
        raise FileNotFoundError("Impossible to locate the engine")

    return path
