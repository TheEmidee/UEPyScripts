"""
The Workspace: the project, its config and its engine, resolved together from
one uproject. Every command starts from here.

The project and config are resolved when the Workspace is built. The engine is
only located the first time something asks for it, so commands that only need
the config (like ci.cleanup) work on machines without an engine.

The machine facts come in through two seams, with the real adapters as
defaults: the Engine locator (the Windows registry and the environment) and the
process runner that launches Engine tools. Tests pass a fake registry or a
recording runner.

Every failure is raised as a WorkspaceError subclass, including a uproject or
Build.version that exists but is malformed. Only the command line edge
(open_workspace) turns them into a fatal log and exit code.
"""

import argparse
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from uepyscripts import logger
from uepyscripts.internal.config import Config
from uepyscripts.internal.engine import Engine
from uepyscripts.internal.engine_locator import EngineLocator
from uepyscripts.internal.errors import (
    EngineNotFoundError,
    InvalidEngineError,
    InvalidProjectError,
    ProjectNotFoundError,
    WorkspaceError,
)
from uepyscripts.internal.process import PopenRunner, ProcessRunner
from uepyscripts.internal.project import Project, find_parent_with_project_file

__all__ = [
    "EngineNotFoundError",
    "InvalidEngineError",
    "InvalidProjectError",
    "ProjectNotFoundError",
    "Workspace",
    "WorkspaceError",
    "add_uproject_argument",
    "open_workspace",
]


class Workspace:
    def __init__(
        self,
        uproject_path: Optional[Path] = None,
        *,
        locator: Optional[EngineLocator] = None,
        runner: Optional[ProcessRunner] = None,
    ) -> None:
        """Without a uproject path, searches up from the current folder. The locator
        defaults to the real registry and environment, the runner to real processes."""
        self.project = Project(_find_uproject(uproject_path))
        logger.info(self.project)

        self.config = Config(self.project.project_folders.config / "PyScripts", self.project.root_folder)

        self._locator = locator if locator is not None else EngineLocator()
        self._runner: ProcessRunner = runner if runner is not None else PopenRunner()
        self._engine: Optional[Engine] = None

    @property
    def engine(self) -> Engine:
        """Located on first access. A successful lookup is cached; a failed one
        is not, so the next access tries again."""
        if self._engine is None:
            try:
                root_path = self._locator.locate(self.project)
            except FileNotFoundError as e:
                raise EngineNotFoundError(str(e)) from e

            self._engine = Engine(self.project, root_path, self._runner)
            logger.info(self._engine)

        return self._engine


def _find_uproject(uproject_path: Optional[Path]) -> Path:
    if uproject_path is None:
        start = Path.cwd()
        found = find_parent_with_project_file(start)
        if found is None:
            raise ProjectNotFoundError(f"Could not find a uproject file from {start}")
        uproject_path = found
    elif not uproject_path.is_file():
        raise ProjectNotFoundError(f"{uproject_path} is not a valid file")

    logger.debug(f"Found uproject file at {uproject_path}")
    return uproject_path


def add_uproject_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--uproject-path",
        type=Path,
        default=None,
        help="Path to the .uproject file. If not set, it is searched for from the current folder upwards.",
    )


@contextmanager
def open_workspace(args: argparse.Namespace, *, runner: Optional[ProcessRunner] = None) -> Iterator[Workspace]:
    """Builds the Workspace from the parsed `--uproject-path` argument. Engine
    tools launch through `runner`, real processes by default.

    Any WorkspaceError raised while building it, or inside the `with` block
    (for example when the engine is first accessed), is logged as fatal and
    exits with code 1. Every other exception propagates untouched."""
    try:
        yield Workspace(args.uproject_path, runner=runner)
    except WorkspaceError as e:
        logger.fatal(f"{type(e).__name__}: {e}")
        sys.exit(1)
