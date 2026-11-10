import argparse
import shutil
import socket
from typing import Optional, Sequence

from ... import logger
from ...internal.config import Config
from ...internal.workspace import add_uproject_argument, open_workspace


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Execute a buildgraph task using a shared storage.")
    parser.add_argument("--build_tag", type=str, help="The tag that will be used to define a folder on a shared storage")
    add_uproject_argument(parser)

    return parser.parse_args(argv)


def delete_buildgraph_shared_storage_directory(config: Config, build_tag: str) -> None:
    shared_storage_dir = config.jenkins.buildgraph_shared_storage_path / build_tag

    logger.info(f"Delete Buildgraph Shared Storage directory: {shared_storage_dir}")
    shutil.rmtree(shared_storage_dir, ignore_errors=True)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_arguments(argv)

    if not args.build_tag:
        raise ValueError("Build tag is required")

    logger.debug(f"Running ci.buildgraph with build tag: {args.build_tag} on machine {socket.gethostname()}")

    # Only the config is needed: the engine is never located, so this runs on machines without one.
    with open_workspace(args) as workspace:
        delete_buildgraph_shared_storage_directory(workspace.config, args.build_tag)


if __name__ == "__main__":
    main()
