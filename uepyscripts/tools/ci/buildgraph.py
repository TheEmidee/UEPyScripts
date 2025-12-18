import argparse
import os
from pathlib import Path
import socket
import shutil
from typing import List

from ... import logger
from ...context import config
from ...context import project
from ...run import buildgraph

def update_or_add_argument(args_list : List[str], arg_name : str, new_values : List[str]) -> List[str]:
    """Update an argument's value(s) if it exists, or add it if it doesn't.
    
    Args:
        args_list: List of command line arguments
        arg_name: The argument name (e.g., "--output-dir")
        new_value: Single value (str) or list of values
    """
    updated_args = []
    i = 0
    found = False
    
    while i < len(args_list):
        if args_list[i] == arg_name:
            updated_args.append(args_list[i])
            updated_args.append( " ".join( [ args_list[i+1] ] + new_values ))
            i += 2
            found = True
        elif args_list[i].startswith(f"{arg_name}="):
            # Handle --arg=value format (only works with single value)
            if len(new_values) == 1:
                updated_args.append(f"{arg_name}={new_values[0]}")
            else:
                # Convert to separate format for multiple values
                updated_args.append(arg_name)
                updated_args.extend(new_values)
            i += 1
            found = True
        else:
            updated_args.append(args_list[i])
            i += 1
    
    if not found:
        updated_args.append(arg_name)
        updated_args.extend(new_values)
    
    return updated_args

def parse_arguments(argv=None):
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Execute a buildgraph task using a shared storage."
    )
    parser.add_argument(
        "--target", 
        type=str, 
        help="The target to run in the buildgraph file"
    )
    parser.add_argument(
        "--build_tag", 
        type=str, 
        help="The tag that will be used to define a folder on a shared storage"
    )

    args, unknown_args = parser.parse_known_args(argv)
    return args, unknown_args

def remove_task_shared_storage_dir(shared_storage_dir: Path, task_name: str) -> None:
    task_shared_storage_dir = shared_storage_dir / task_name
    logger.info(f"Remove task shared storage directory: {task_shared_storage_dir}")
    shutil.rmtree(task_shared_storage_dir, ignore_errors=True)

def try_delete_local_buildgraph_folder(build_tag : str) -> None:
    if not project.project_folders.saved.exists():
        logger.info(f"Project saved folder does not exist: {project.project_folders.saved}. Creating it")
        os.makedirs(project.project_folders.saved, exist_ok=True)

    buildgraph_local_folder = project.project_folders.saved_folders.buildgraph
    ci_task_version_file = buildgraph_local_folder / "CITaskVersionFile.txt"

    logger.info(f"Managing file CITaskVersionFile.txt in {buildgraph_local_folder}")

    def write_tag_to_file():
        logger.info(f"Writing build tag {build_tag} to {ci_task_version_file}")
        Path(buildgraph_local_folder).mkdir(parents=True, exist_ok=True)

        with open(ci_task_version_file, "w") as file:
            file.write(build_tag)

    if ci_task_version_file.exists():
        logger.info(f"Found CITaskVersionFile.txt")
        with open(ci_task_version_file, "r") as file:
            current_build_tag = file.read().strip()
            if current_build_tag != build_tag:
                logger.info(f"Current build tag {current_build_tag} does not match {build_tag}. Remove local folder {buildgraph_local_folder}")
                shutil.rmtree(buildgraph_local_folder, ignore_errors=True)
                write_tag_to_file()
    else:
        logger.info("Cannot find CITaskVersionFile.txt")
        write_tag_to_file()

def cleanup_local_folder():
    def remove_folder(folder: Path):
        if folder.exists():
            logger.info(f"Removing folder: {folder}")
            shutil.rmtree(folder, ignore_errors=True)
    
    remove_folder(project.project_folders.saved_folders.jenkins)
    remove_folder(project.project_folders.saved_folders.tests)

def main(argv=None):
    args, unknown_args = parse_arguments(argv)

    if not args.build_tag:
        raise ValueError("Build tag is required")
    
    logger.debug(f"Running ci.buildgraph with build tag: {args.build_tag} on machine {socket.gethostname()}")

    shared_storage_dir = Path(config["Jenkins"]["BuildgraphSharedStoragePath"]) / args.build_tag
    logger.debug(f"Shared storage directory: {shared_storage_dir}")

    remove_task_shared_storage_dir(shared_storage_dir, args.target)
    try_delete_local_buildgraph_folder(args.build_tag)
    cleanup_local_folder()

    # Because it's a mess to correctly pass the properties as a JSON string from the jenkinsfile through a power shell script,
    # all the properties for the buildgraph task are passed as a single string argument like "-set:XXX=YYY -set:ZZZ=WWW"
    # What we do here is just pass every argument in this string_argument parameter
    updated_args = update_or_add_argument(unknown_args, "--string_arguments", [
        "-BuildMachine",
        f'-SharedStorageDir="{shared_storage_dir}"',
        "-WriteToSharedStorage",
        f"-SingleNode=\"{args.target}\"",
        "-NoP4"
    ] )

    buildgraph.main(updated_args)

if __name__ == '__main__':
    main()