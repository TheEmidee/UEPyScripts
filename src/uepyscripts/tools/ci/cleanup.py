import argparse
import socket
from typing import Optional, Sequence

from ... import logger
from ...internal.workspace import add_uproject_argument, open_workspace
from .shared_storage import SharedStorage


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Delete the Shared storage of a finished CI build.")
    parser.add_argument("--build_tag", type=str, required=True, help="The Build tag whose Shared storage folder is deleted")
    add_uproject_argument(parser)

    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_arguments(argv)

    logger.debug(f"Running ci.cleanup with build tag: {args.build_tag} on machine {socket.gethostname()}")

    # Only the config is needed: the engine is never located, so this runs on machines without one.
    with open_workspace(args) as workspace:
        SharedStorage.for_build(workspace, args.build_tag).delete()


if __name__ == "__main__":
    main()
