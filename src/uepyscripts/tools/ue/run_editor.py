import argparse
from typing import Optional, Sequence

from uepyscripts.internal.process import ProcessRunner
from uepyscripts.internal.workspace import add_uproject_argument, open_workspace


def main(argv: Optional[Sequence[str]] = None, *, runner: Optional[ProcessRunner] = None) -> None:
    parser = argparse.ArgumentParser(description="Start the Unreal Editor for the project.")
    add_uproject_argument(parser)
    args = parser.parse_args(argv)

    with open_workspace(args, runner=runner) as workspace:
        print("Starting Unreal Editor...")
        workspace.engine.launch_editor()


if __name__ == "__main__":
    main()
