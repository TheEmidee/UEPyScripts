import argparse
import os
import shutil
import socket
from pathlib import Path
from typing import List, Optional, Sequence

from ... import logger
from ...context import config, project
from ...run import buildgraph


def update_or_add_argument(existing_args: list[str], defaults: list[str]) -> List[str]:
    """Update an argument's value(s) if it exists, or add it if it doesn't.

    Args:
        args_list: List of command line arguments
        arg_name: The argument name (e.g., "--output-dir")
        new_value: Single value (str) or list of values
    """
    """
    Combines existing arguments with defaults. 
    If a default argument's key is already present in existing_args, 
    the existing one is preserved.
    """

    def get_arg_key(arg: str) -> str:
        # Special case for Unreal -set:Key=Value pairs
        # The 'key' here is actually "-set:VariableName"
        if arg.startswith("-set:"):
            return arg.split("=", 1)[0]

        # Standard flags or Key=Value pairs
        # Splits on '=' or ':' and takes the first part (e.g., -NoP4 or -SharedStorageDir)
        return arg.split("=", 1)[0].split(":", 1)[0]

    # Map the keys already present in the command line
    existing_keys = {get_arg_key(arg) for arg in existing_args}

    # Start with all the arguments the user actually typed
    final_args = list(existing_args)

    for default_arg in defaults:
        # Only add the default if the key isn't already there
        if get_arg_key(default_arg) not in existing_keys:
            final_args.append(default_arg)

    return final_args


def parse_arguments(argv: Optional[Sequence[str]] = None) -> tuple[argparse.Namespace, list[str]]:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Execute a buildgraph task using a shared storage.")
    parser.add_argument("--target", type=str, help="The target to run in the buildgraph file")
    parser.add_argument("--build_tag", type=str, help="The tag that will be used to define a folder on a shared storage")
    parser.add_argument(
        "--no-single-node",
        action="store_true",
        help="Set this flag to not use SingleNode but use Target. This also disables using the shared storage dir.",
    )

    args, unknown_args = parser.parse_known_args(argv)
    return args, unknown_args


def remove_task_shared_storage_dir(shared_storage_dir: Path, task_name: str) -> None:
    task_shared_storage_dir = shared_storage_dir / task_name
    logger.info(f"Remove task shared storage directory: {task_shared_storage_dir}")
    shutil.rmtree(task_shared_storage_dir, ignore_errors=True)


def try_delete_local_buildgraph_folder(build_tag: str) -> None:
    if not project.project_folders.saved.exists():
        logger.info(f"Project saved folder does not exist: {project.project_folders.saved}. Creating it")
        os.makedirs(project.project_folders.saved, exist_ok=True)

    buildgraph_local_folder = project.project_folders.saved_folders.buildgraph
    ci_task_version_file = buildgraph_local_folder / "CITaskVersionFile.txt"

    logger.info(f"Managing file CITaskVersionFile.txt in {buildgraph_local_folder}")

    def write_tag_to_file() -> None:
        logger.info(f"Writing build tag {build_tag} to {ci_task_version_file}")
        Path(buildgraph_local_folder).mkdir(parents=True, exist_ok=True)

        with open(ci_task_version_file, "w") as file:
            file.write(build_tag)

    if ci_task_version_file.exists():
        logger.info("Found CITaskVersionFile.txt")
        with open(ci_task_version_file, "r") as file:
            current_build_tag = file.read().strip()
            if current_build_tag != build_tag:
                logger.info(f"Current build tag {current_build_tag} does not match {build_tag}. Remove local folder {buildgraph_local_folder}")
                shutil.rmtree(buildgraph_local_folder, ignore_errors=True)
                write_tag_to_file()
    else:
        logger.info("Cannot find CITaskVersionFile.txt")
        write_tag_to_file()


def cleanup_local_folder() -> None:
    def remove_folder(folder: Path) -> None:
        if folder.exists():
            logger.info(f"Removing folder: {folder}")
            shutil.rmtree(folder, ignore_errors=True)

    remove_folder(project.project_folders.saved_folders.jenkins)
    remove_folder(project.project_folders.saved_folders.tests)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args, unknown_args = parse_arguments(argv)

    if not args.target:
        raise ValueError("Target is required")
    if not args.build_tag:
        raise ValueError("Build tag is required")

    logger.info(f"Running ci.buildgraph with build tag: {args.build_tag} on machine {socket.gethostname()}")

    default_arguments: list[str] = ["-BuildMachine", "-NoP4"]

    if args.no_single_node:
        logger.info("The flag --no-single-node was passed. Run the task with Target and not with SingleNode")
        default_arguments += [f"--target={args.target}"]
    else:
        shared_storage_dir = Path(config["Jenkins"]["BuildgraphSharedStoragePath"]) / args.build_tag
        logger.info(f"Shared storage directory: {shared_storage_dir}")

        remove_task_shared_storage_dir(shared_storage_dir, args.target)
        try_delete_local_buildgraph_folder(args.build_tag)
        cleanup_local_folder()

        default_arguments += [f"-SharedStorageDir={shared_storage_dir}", "-WriteToSharedStorage", f"-SingleNode={args.target}"]

    updated_args = update_or_add_argument(unknown_args, default_arguments)

    return buildgraph.main(updated_args)


if __name__ == "__main__":
    main()
