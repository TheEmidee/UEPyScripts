import os
import winreg
from pathlib import Path
from typing import Optional

from ..internal.project import Project
from ..tools.helpers import get_engine_root_folder_from_env_var, is_engine_from_egs
from ..tools.winreg import get_registry_value


def resolve_engine_from_env_var(project: Project) -> Optional[Path]:
    return get_engine_root_folder_from_env_var(project.engine_association)


def resolve_engine_from_registry(project: Project) -> Optional[Path]:
    path = get_registry_value(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Epic Games\Unreal Engine\Builds", project.engine_association)
    if path:
        path = Path(path)
        if path.exists():
            return path

    return None


def resolve_engine_from_egs(project: Project) -> Optional[Path]:
    if is_engine_from_egs(project.engine_association):
        registry_value = get_registry_value(
            winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\EpicGames\Unreal Engine\{project.engine_association}", "InstalledDirectory"
        )
        if registry_value:
            path = Path(registry_value)
            if path.exists():
                return path

    return None


def resolve_engine_from_path(project: Project) -> Optional[Path]:
    path = Path(project.engine_association)
    if os.path.isabs(path):
        return path

    return None


def resolve_engine_path(project: Project) -> Path:
    resolvers = [
        resolve_engine_from_env_var,
        resolve_engine_from_registry,
        resolve_engine_from_egs,
        resolve_engine_from_path,
    ]

    for resolver in resolvers:
        path = resolver(project)
        if path:
            break
    else:
        raise FileNotFoundError("Impossible to locate the engine")

    if not (path.exists() and str(path).replace(" ", "") not in ["", ".", "\\"]):
        raise FileNotFoundError("Impossible to locate the engine")

    return path
