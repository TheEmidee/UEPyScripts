import argparse
import shutil
import socket
from pathlib import Path
from typing import Optional, Sequence

from ... import logger
from ...context import config


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Execute a buildgraph task using a shared storage.")
    parser.add_argument("--build_tag", type=str, help="The tag that will be used to define a folder on a shared storage")

    return parser.parse_args(argv)


def delete_buildgraph_shared_storage_directory(build_tag: str) -> None:
    shared_storage_dir = Path(f"{config['Jenkins']['BuildgraphSharedStoragePath']}\{build_tag}")

    logger.info(f"Delete Buildgraph Shared Storage directory: {shared_storage_dir}")
    shutil.rmtree(shared_storage_dir, ignore_errors=True)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_arguments(argv)

    if not args.build_tag:
        raise ValueError("Build tag is required")

    logger.debug(f"Running ci.buildgraph with build tag: {args.build_tag} on machine {socket.gethostname()}")
    delete_buildgraph_shared_storage_directory(args.build_tag)


if __name__ == "__main__":
    main()
