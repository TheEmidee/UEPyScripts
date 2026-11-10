"""
The Engine locator: finds the root folder of the engine a project needs.

Every machine fact it relies on (the Windows registry and the environment,
which also gives the launcher's %PROGRAMDATA% folder) comes in through the
constructor, so the whole lookup can be exercised with a dict-backed registry
and a dict environment.

The lookup tries, in order:
1. the folder layout: a Native project's engine is the parent of its folder
2. a build registered under HKCU\\SOFTWARE\\Epic Games\\Unreal Engine\\Builds
3. an Epic Games Launcher install (registry, then LauncherInstalled.dat)
4. the Engine association read as a path, absolute or relative to the project
5. the NODE_UE_ROOT environment variable, joined with the Engine association
"""

import os
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Literal, Optional, Protocol

from pydantic import BaseModel

from uepyscripts import logger
from uepyscripts.internal.project import Project

Hive = Literal["HKCU", "HKLM"]

REGISTERED_BUILDS_KEY = r"SOFTWARE\Epic Games\Unreal Engine\Builds"
LAUNCHER_INSTALL_KEY = r"SOFTWARE\EpicGames\Unreal Engine"
LAUNCHER_MANIFEST = Path("Epic", "UnrealEngineLauncher", "LauncherInstalled.dat")
ENGINE_ROOT_ENV_VAR = "NODE_UE_ROOT"


class Registry(Protocol):
    def read(self, hive: Hive, key: str, name: str) -> Optional[str]:
        """The string value `name` under `hive\\key`, or None when the key or value doesn't exist."""
        ...


class WindowsRegistry:
    """Reads the real Windows registry."""

    def read(self, hive: Hive, key: str, name: str) -> Optional[str]:
        import winreg

        hkey = winreg.HKEY_CURRENT_USER if hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        full_path = f"{hive}\\{key}\\{name}"

        try:
            with winreg.OpenKey(hkey, key) as opened_key:
                value, _ = winreg.QueryValueEx(opened_key, name)
                return str(value)
        except FileNotFoundError:
            logger.debug(f"No string value in the registry for the key {full_path}")
        except Exception as e:
            logger.fatal(f"An error occurred when trying to read {full_path}: {e}")

        return None


class _LauncherInstallation(BaseModel):
    InstallLocation: str
    AppName: str
    AppVersion: str


class _LauncherManifest(BaseModel):
    InstallationList: list[_LauncherInstallation]


def _is_launcher_version(engine_association: str) -> bool:
    """Launcher installs are associated by version number, like 5.4 or 5.0EA."""
    return re.search(r"^[45]\.[0-9]+(EA)?$", engine_association) is not None


class EngineLocator:
    def __init__(self, registry: Optional[Registry] = None, environ: Optional[Mapping[str, str]] = None) -> None:
        self._registry: Registry = registry if registry is not None else WindowsRegistry()
        self._environ: Mapping[str, str] = environ if environ is not None else os.environ

    def locate(self, project: Project) -> Path:
        """The engine root folder for the project. Raises FileNotFoundError when no
        step finds one, or when the first step that answers gives a folder that
        doesn't exist."""
        steps: list[tuple[str, Callable[[Project], Optional[Path]]]] = [
            ("native project", self._from_native_project),
            ("registered build", self._from_registered_build),
            ("launcher install", self._from_launcher),
            ("engine association path", self._from_association_path),
            # Last, so a machine that has the variable but installed the engine
            # with the launcher still finds the launcher install.
            (ENGINE_ROOT_ENV_VAR, self._from_env_var),
        ]

        for name, step in steps:
            path = step(project)
            if path:
                logger.info(f"Engine path resolved via '{name}': {path}")
                break
        else:
            raise FileNotFoundError("Impossible to locate the engine")

        # Reject a missing folder, or a degenerate path made only of . or \
        if not path.exists() or str(path).strip() in ["", ".", "\\"]:
            raise FileNotFoundError(f"Impossible to locate the engine: {path} does not exist")

        return path

    def _from_native_project(self, project: Project) -> Optional[Path]:
        if project.is_native_project:
            return project.root_folder.parent

        return None

    def _from_registered_build(self, project: Project) -> Optional[Path]:
        value = self._registry.read("HKCU", REGISTERED_BUILDS_KEY, project.engine_association)
        return Path(value) if value else None

    def _from_launcher(self, project: Project) -> Optional[Path]:
        if _is_launcher_version(project.engine_association):
            value = self._registry.read("HKLM", rf"{LAUNCHER_INSTALL_KEY}\{project.engine_association}", "InstalledDirectory")
            if value:
                return Path(value)

        # Some installations are only listed in the launcher's manifest
        program_data = self._environ.get("PROGRAMDATA")
        if not program_data:
            return None

        manifest_path = Path(program_data) / LAUNCHER_MANIFEST
        if not manifest_path.exists():
            return None

        try:
            manifest = _LauncherManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Error parsing manifest {manifest_path}: {e}")
            return None

        for installation in manifest.InstallationList:
            if installation.AppName.startswith("UE_") and installation.AppVersion.startswith(project.engine_association):
                return Path(installation.InstallLocation)

        return None

    def _from_association_path(self, project: Project) -> Optional[Path]:
        path = Path(project.engine_association)
        if not path.is_absolute():
            path = (project.root_folder / path).resolve()

        # Only answer for a folder that exists: a well-formed path to nothing would
        # stop the lookup before the NODE_UE_ROOT step gets its turn.
        return path if path.exists() else None

    def _from_env_var(self, project: Project) -> Optional[Path]:
        engine_root = self._environ.get(ENGINE_ROOT_ENV_VAR)
        if not engine_root:
            return None

        path = Path(engine_root)
        if project.engine_association:
            path = path / project.engine_association

        return path
