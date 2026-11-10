import argparse
import os
import shutil
import socket
from pathlib import Path
from typing import Optional, Sequence

from ... import logger
from ...internal.buildgraph import BuildGraphCommand
from ...internal.project import Project
from ...internal.workspace import add_uproject_argument, open_workspace


def parse_arguments(argv: Optional[Sequence[str]] = None) -> tuple[argparse.Namespace, list[str]]:
    """Parse command line arguments. Unknown arguments are passed to BuildGraph."""
    parser = argparse.ArgumentParser(description="Execute a buildgraph task using a shared storage.")
    parser.add_argument("--target", type=str, help="The node (or, with --no-single-node, the target) to run in the buildgraph file")
    parser.add_argument("--build_tag", type=str, help="The tag that will be used to define a folder on a shared storage")
    parser.add_argument(
        "--no-single-node",
        action="store_true",
        help="Set this flag to not use SingleNode but use Target. This also disables using the shared storage dir.",
    )
    parser.add_argument("--script", type=Path, default=None, help="Path to the buildgraph XML file. If not set, [Project] BuildgraphPath is used.")
    add_uproject_argument(parser)

    return parser.parse_known_args(argv)


def prepare_ci_folders(project: Project, shared_storage_dir: Path, build_tag: str, task_name: str) -> None:
    """Gets the machine ready to run one Single node of a CI build:
    - removes the task's folder from the shared storage, so stale outputs never get reused
    - clears the local Saved/BuildGraph folder when it holds the state of another build tag
      (tracked in Saved/BuildGraph/CITaskVersionFile.txt)
    - removes Saved/Jenkins and Saved/Tests"""
    task_shared_storage_dir = shared_storage_dir / task_name
    logger.info(f"Remove task shared storage directory: {task_shared_storage_dir}")
    shutil.rmtree(task_shared_storage_dir, ignore_errors=True)

    _reset_local_buildgraph_folder(project, build_tag)

    for folder in [project.project_folders.saved_folders.jenkins, project.project_folders.saved_folders.tests]:
        if folder.exists():
            logger.info(f"Removing folder: {folder}")
            shutil.rmtree(folder, ignore_errors=True)


def _reset_local_buildgraph_folder(project: Project, build_tag: str) -> None:
    if not project.project_folders.saved.exists():
        logger.info(f"Project saved folder does not exist: {project.project_folders.saved}. Creating it")
        os.makedirs(project.project_folders.saved, exist_ok=True)

    buildgraph_local_folder = project.project_folders.saved_folders.buildgraph
    ci_task_version_file = buildgraph_local_folder / "CITaskVersionFile.txt"

    logger.info(f"Managing file CITaskVersionFile.txt in {buildgraph_local_folder}")

    def write_tag_to_file() -> None:
        logger.info(f"Writing build tag {build_tag} to {ci_task_version_file}")
        buildgraph_local_folder.mkdir(parents=True, exist_ok=True)
        ci_task_version_file.write_text(build_tag)

    if not ci_task_version_file.exists():
        logger.info("Cannot find CITaskVersionFile.txt")
        write_tag_to_file()
        return

    logger.info("Found CITaskVersionFile.txt")
    current_build_tag = ci_task_version_file.read_text().strip()
    if current_build_tag != build_tag:
        logger.info(f"Current build tag {current_build_tag} does not match {build_tag}. Remove local folder {buildgraph_local_folder}")
        shutil.rmtree(buildgraph_local_folder, ignore_errors=True)
        write_tag_to_file()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args, extra_arguments = parse_arguments(argv)

    if not args.target:
        raise ValueError("Target is required")
    if not args.build_tag:
        raise ValueError("Build tag is required")

    logger.info(f"Running ci.buildgraph with build tag: {args.build_tag} on machine {socket.gethostname()}")

    with open_workspace(args) as workspace:
        if args.no_single_node:
            logger.info("The flag --no-single-node was passed. Run the task with Target and not with SingleNode")
            command = BuildGraphCommand.for_workspace(
                workspace, target=args.target, script=args.script, extra_args=extra_arguments, build_machine=True, no_p4=True
            )
        else:
            shared_storage_dir = workspace.config.jenkins.buildgraph_shared_storage_path / args.build_tag
            logger.info(f"Shared storage directory: {shared_storage_dir}")

            prepare_ci_folders(workspace.project, shared_storage_dir, args.build_tag, args.target)

            command = BuildGraphCommand.for_workspace(
                workspace,
                single_node=args.target,
                script=args.script,
                extra_args=extra_arguments,
                build_machine=True,
                no_p4=True,
                shared_storage=shared_storage_dir,
                write_to_shared_storage=True,
            )

        return workspace.engine.uat(command.uat_arguments())


if __name__ == "__main__":
    main()
