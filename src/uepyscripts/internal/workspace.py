"""
The Workspace: the project, its config and its engine, resolved together from
one uproject. Every command starts from here.

The project and config are resolved when the Workspace is built. The engine is
only located the first time something asks for it, so commands that only need
the config (like ci.cleanup) work on machines without an engine.

Failures are raised as WorkspaceError subclasses. Only the command line edge
(open_workspace) turns them into a fatal log and exit code.
"""

import argparse
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from uepyscripts import logger
from uepyscripts.internal.config import Config, resolve_config
from uepyscripts.internal.engine import Engine, resolve_engine
from uepyscripts.internal.project import Project, resolve_project


class WorkspaceError(Exception):
    """Base class for everything that can go wrong while resolving a Workspace."""


class ProjectNotFoundError(WorkspaceError):
    """No uproject was found by searching up from the current folder, or the given path doesn't exist."""


class EngineNotFoundError(WorkspaceError):
    """The engine the project needs could not be located."""


class Workspace:
    def __init__(self, uproject_path: Optional[Path] = None) -> None:
        """Without a uproject path, searches up from the current folder."""
        try:
            self.project: Project = resolve_project(uproject_path)
        except FileNotFoundError as e:
            raise ProjectNotFoundError(str(e)) from e

        self.config: Config = resolve_config(self.project)
        self._engine: Optional[Engine] = None

    @property
    def engine(self) -> Engine:
        """Located on first access. A successful lookup is cached; a failed one
        is not, so the next access tries again."""
        if self._engine is None:
            try:
                self._engine = resolve_engine(self.project)
            except FileNotFoundError as e:
                raise EngineNotFoundError(str(e)) from e

        return self._engine


def add_uproject_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--uproject-path",
        type=Path,
        default=None,
        help="Path to the .uproject file. If not set, it is searched for from the current folder upwards.",
    )


@contextmanager
def open_workspace(args: argparse.Namespace) -> Iterator[Workspace]:
    """Builds the Workspace from the parsed `--uproject-path` argument.

    Any WorkspaceError raised while building it, or inside the `with` block
    (for example when the engine is first accessed), is logged as fatal and
    exits with code 1. Every other exception propagates untouched."""
    try:
        yield Workspace(args.uproject_path)
    except WorkspaceError as e:
        logger.fatal(f"{type(e).__name__}: {e}")
        sys.exit(1)
