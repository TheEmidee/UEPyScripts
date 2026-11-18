import argparse
from typing import Optional, Sequence

from uepyscripts.internal.process import ProcessRunner
from uepyscripts.internal.workspace import add_uproject_argument, open_workspace


def main(argv: Optional[Sequence[str]] = None, *, runner: Optional[ProcessRunner] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run UAT. Every argument except --uproject-path is forwarded to UAT.", allow_abbrev=False, add_help=False
    )
    add_uproject_argument(parser)

    args, forwarded_arguments = parser.parse_known_args(argv)

    with open_workspace(args, runner=runner) as workspace:
        return workspace.engine.uat(forwarded_arguments)


if __name__ == "__main__":
    main()
