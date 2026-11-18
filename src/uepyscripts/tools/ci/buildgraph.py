import argparse
import socket
from pathlib import Path
from typing import Optional, Sequence

from ... import logger
from ...internal.buildgraph import BuildGraphCommand, Target
from ...internal.process import ProcessRunner
from ...internal.workspace import add_uproject_argument, open_workspace
from .single_node import single_node_command


def parse_arguments(argv: Optional[Sequence[str]] = None) -> tuple[argparse.Namespace, list[str]]:
    """Parse command line arguments. Unknown arguments are passed to BuildGraph."""
    parser = argparse.ArgumentParser(description="Execute a buildgraph task using a shared storage.")
    parser.add_argument("--target", type=str, required=True, help="The node (or, with --no-single-node, the target) to run in the buildgraph file")
    parser.add_argument("--build_tag", type=str, required=True, help="The Build tag, which names the build's Shared storage folder")
    parser.add_argument(
        "--no-single-node",
        action="store_true",
        help="Set this flag to not use SingleNode but use Target. This also disables using the shared storage dir.",
    )
    parser.add_argument("--script", type=Path, default=None, help="Path to the buildgraph XML file. If not set, [Project] BuildgraphPath is used.")
    add_uproject_argument(parser)

    return parser.parse_known_args(argv)


def main(argv: Optional[Sequence[str]] = None, *, runner: Optional[ProcessRunner] = None) -> int:
    args, extra_arguments = parse_arguments(argv)

    logger.info(f"Running ci.buildgraph with build tag: {args.build_tag} on machine {socket.gethostname()}")

    with open_workspace(args, runner=runner) as workspace:
        if args.no_single_node:
            logger.info("The flag --no-single-node was passed. Run the task with Target and not with SingleNode")
            command = BuildGraphCommand.for_workspace(
                workspace, Target(args.target), script=args.script, extra_args=extra_arguments, build_machine=True
            )
        else:
            command = single_node_command(workspace, args.target, args.build_tag, script=args.script, extra_args=extra_arguments)

        return workspace.engine.uat(command.uat_arguments())


if __name__ == "__main__":
    main()
