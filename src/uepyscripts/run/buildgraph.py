import argparse
from pathlib import Path
from typing import Optional, Sequence

from .. import logger
from ..internal.buildgraph import BuildGraphCommand
from ..internal.workspace import add_uproject_argument, open_workspace


def parse_arguments(argv: Optional[Sequence[str]] = None) -> tuple[argparse.Namespace, list[str]]:
    """Parse command line arguments. Unknown arguments are passed to BuildGraph."""
    parser = argparse.ArgumentParser(description="Execute a buildgraph target. Every unknown argument is passed to BuildGraph.")
    parser.add_argument("--target", type=str, required=True, help="The target to run in the buildgraph file")
    parser.add_argument("--script", type=Path, default=None, help="Path to the buildgraph XML file. If not set, [Project] BuildgraphPath is used.")
    add_uproject_argument(parser)
    return parser.parse_known_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args, extra_arguments = parse_arguments(argv)

    logger.info(f"Run Buildgraph - Target : {args.target}")
    logger.info(f"Arguments : {extra_arguments}")

    with open_workspace(args) as workspace:
        command = BuildGraphCommand.for_workspace(workspace, target=args.target, script=args.script, extra_args=extra_arguments)
        return workspace.engine.uat(command.uat_arguments())


if __name__ == "__main__":
    main()
