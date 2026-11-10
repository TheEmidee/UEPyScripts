"""
The Shared storage of one CI build: the folder where its Single nodes exchange
their outputs, `[Jenkins] BuildgraphSharedStoragePath / <Build tag>`, with one
subfolder per Single node.

Removing a Shared storage folder fails loudly: a folder left behind either
feeds stale outputs to the next run of a Single node, or keeps a finished
build's outputs on the share. A folder that is already gone is fine. The
machine-local resets in `prepare_single_node` only affect that machine's
cache, so their errors are ignored.
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from uepyscripts import logger
from uepyscripts.internal.project import Project
from uepyscripts.internal.workspace import Workspace

BUILD_TAG_FILE = "CITaskVersionFile.txt"


@dataclass(frozen=True)
class SharedStorage:
    project: Project
    build_tag: str
    path: Path

    @classmethod
    def for_build(cls, workspace: Workspace, build_tag: str) -> "SharedStorage":
        """Raises ConfigError when `[Jenkins] BuildgraphSharedStoragePath` is missing."""
        path = workspace.config.jenkins.buildgraph_shared_storage_path / build_tag
        logger.info(f"Shared storage of {build_tag}: {path}")
        return cls(workspace.project, build_tag, path)

    def prepare_single_node(self, node: str) -> None:
        """Gets this machine ready to run `node` as a Single node of the build:
        - removes the node's subfolder, so its stale outputs are never reused
        - clears the local Saved/BuildGraph folder when it holds the state of
          another Build tag (recorded in Saved/BuildGraph/CITaskVersionFile.txt)
        - removes Saved/Jenkins and Saved/Tests"""
        _remove_shared_folder(self.path / node)
        self._reset_local_buildgraph_folder()

        saved_folders = self.project.project_folders.saved_folders
        for folder in [saved_folders.jenkins, saved_folders.tests]:
            if folder.exists():
                logger.info(f"Removing folder: {folder}")
                shutil.rmtree(folder, ignore_errors=True)

    def delete(self) -> None:
        """Removes the whole build's folder, once the build is over."""
        _remove_shared_folder(self.path)

    def _reset_local_buildgraph_folder(self) -> None:
        local_folder = self.project.project_folders.saved_folders.buildgraph
        tag_file = local_folder / BUILD_TAG_FILE

        if tag_file.exists():
            local_tag = tag_file.read_text().strip()
            if local_tag == self.build_tag:
                return

            logger.info(f"{local_folder} holds the state of {local_tag}, not {self.build_tag}: removing it")
            shutil.rmtree(local_folder, ignore_errors=True)

        local_folder.mkdir(parents=True, exist_ok=True)
        tag_file.write_text(self.build_tag)


def _remove_shared_folder(path: Path) -> None:
    if not path.exists():
        return

    logger.info(f"Removing Shared storage folder: {path}")
    shutil.rmtree(path)
