"""
Getting a Single node of a CI build ready to run: the BuildGraph command that
runs it, on a build machine, with the Shared storage of its Build tag.

`single_node_command` does it in this order:
  1. build and validate the BuildGraph command (the Shared storage path, the
     script, the script folders and the properties). Any failure is raised
     here, before anything on disk changes
  2. remove the node's subfolder of the Shared storage, so its stale outputs
     are never reused. A subfolder that can't be removed stops here
  3. reset this machine: clear the local Saved/BuildGraph folder when it holds
     the state of another Build tag (recorded in
     Saved/BuildGraph/CITaskVersionFile.txt), and remove Saved/Jenkins and
     Saved/Tests. These only affect this machine's cache, so their errors are
     ignored

Running the command is the caller's job.
"""

import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

from uepyscripts import logger
from uepyscripts.internal.buildgraph import BuildGraphCommand, SingleNode
from uepyscripts.internal.project import Project
from uepyscripts.internal.workspace import Workspace
from uepyscripts.tools.ci.shared_storage import SharedStorage

BUILD_TAG_FILE = "CITaskVersionFile.txt"


def single_node_command(
    workspace: Workspace,
    node: str,
    build_tag: str,
    *,
    script: Optional[Path] = None,
    extra_args: Sequence[str] = (),
) -> BuildGraphCommand:
    """The BuildGraph command that runs `node` as a Single node of the build
    `build_tag`, once the Shared storage and this machine are ready for it.

    `script` and `extra_args` are as in `BuildGraphCommand.for_workspace`.
    Raises ConfigError or BuildGraphError, without touching the disk, when
    the command can't be built."""
    shared_storage = SharedStorage.for_build(workspace, build_tag)
    command = BuildGraphCommand.for_workspace(
        workspace,
        SingleNode(node, shared_storage.path),
        script=script,
        extra_args=extra_args,
        build_machine=True,
    )

    shared_storage.clear_node(node)
    _reset_this_machine(workspace.project, build_tag)

    return command


# ---- Internals --------------------------------------------------------


def _reset_this_machine(project: Project, build_tag: str) -> None:
    saved_folders = project.project_folders.saved_folders
    _reset_local_buildgraph_folder(saved_folders.buildgraph, build_tag)

    for folder in [saved_folders.jenkins, saved_folders.tests]:
        if folder.exists():
            logger.info(f"Removing folder: {folder}")
            shutil.rmtree(folder, ignore_errors=True)


def _reset_local_buildgraph_folder(local_folder: Path, build_tag: str) -> None:
    tag_file = local_folder / BUILD_TAG_FILE

    if tag_file.exists():
        local_tag = tag_file.read_text().strip()
        if local_tag == build_tag:
            return

        logger.info(f"{local_folder} holds the state of {local_tag}, not {build_tag}: removing it")
        shutil.rmtree(local_folder, ignore_errors=True)

    local_folder.mkdir(parents=True, exist_ok=True)
    tag_file.write_text(build_tag)
