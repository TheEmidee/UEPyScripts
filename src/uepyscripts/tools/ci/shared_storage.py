"""
The Shared storage of one CI build: the folder where its Single nodes exchange
their outputs, `[Jenkins] BuildgraphSharedStoragePath / <Build tag>`, with one
subfolder per Single node.

Removing a Shared storage folder fails loudly: a folder left behind either
feeds stale outputs to the next run of a Single node, or keeps a finished
build's outputs on the share. A folder that is already gone is fine.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from uepyscripts import logger
from uepyscripts.internal.workspace import Workspace


@dataclass(frozen=True)
class SharedStorage:
    build_tag: str
    path: Path

    @classmethod
    def for_build(cls, workspace: Workspace, build_tag: str) -> "SharedStorage":
        """Raises ConfigError when `[Jenkins] BuildgraphSharedStoragePath` is missing."""
        path = workspace.config.jenkins.buildgraph_shared_storage_path / build_tag
        logger.info(f"Shared storage of {build_tag}: {path}")
        return cls(build_tag, path)

    def clear_node(self, node: str) -> None:
        """Removes the subfolder of the Single node `node`, so its stale outputs are never reused."""
        _remove_shared_folder(self.path / node)

    def delete(self) -> None:
        """Removes the whole build's folder, once the build is over."""
        _remove_shared_folder(self.path)


def _remove_shared_folder(path: Path) -> None:
    if not path.exists():
        return

    logger.info(f"Removing Shared storage folder: {path}")
    shutil.rmtree(path)
