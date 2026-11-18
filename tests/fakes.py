"""Test adapters for the Workspace's seams, and writers for the files it reads."""

import json
from pathlib import Path
from typing import Optional

from uepyscripts.internal.engine_locator import Hive


class RecordingRunner:
    """A process runner that records the argv instead of launching anything."""

    def __init__(self, exit_code: int = 0) -> None:
        self.exit_code = exit_code
        self.ran: list[list[str]] = []
        self.started: list[list[str]] = []

    def run(self, argv: list[str]) -> int:
        self.ran.append(argv)
        return self.exit_code

    def start(self, argv: list[str]) -> None:
        self.started.append(argv)


class DictRegistry:
    """A registry backed by a dict, recording every read."""

    def __init__(self, values: Optional[dict[tuple[Hive, str, str], str]] = None) -> None:
        self.values = values or {}
        self.reads: list[tuple[Hive, str, str]] = []

    def read(self, hive: Hive, key: str, name: str) -> Optional[str]:
        self.reads.append((hive, key, name))
        return self.values.get((hive, key, name))


def write_build_version(root: Path, content: Optional[str] = None) -> Path:
    """Writes `root/Engine/Build/Build.version`, 5.4.2 unless `content` is given."""
    build_folder = root / "Engine" / "Build"
    build_folder.mkdir(parents=True, exist_ok=True)
    build_version = build_folder / "Build.version"
    build_version.write_text(content if content is not None else json.dumps({"MajorVersion": 5, "MinorVersion": 4, "PatchVersion": 2}))
    return build_version


def write_uproject(folder: Path, engine_association: str = "") -> Path:
    """Writes `folder/<folder name>.uproject` with this Engine association."""
    folder.mkdir(parents=True, exist_ok=True)
    uproject = folder / f"{folder.name}.uproject"
    uproject.write_text(json.dumps({"EngineAssociation": engine_association}))
    return uproject


def tool(engine_root: Path, *parts: str) -> str:
    """The path of an Engine tool under `engine_root/Engine`, as the Engine passes it to the runner."""
    return str((engine_root / "Engine").resolve().joinpath(*parts))
