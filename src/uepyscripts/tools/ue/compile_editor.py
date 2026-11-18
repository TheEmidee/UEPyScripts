import argparse
import sys
from typing import Optional, Sequence

from uepyscripts.internal.process import ProcessRunner
from uepyscripts.internal.workspace import add_uproject_argument, open_workspace


def main(argv: Optional[Sequence[str]] = None, *, runner: Optional[ProcessRunner] = None) -> None:
    parser = argparse.ArgumentParser(description="Compile the editor target of the project.")
    add_uproject_argument(parser)
    args = parser.parse_args(argv)

    with open_workspace(args, runner=runner) as workspace:
        print("Compiling Unreal Editor...")
        if workspace.engine.compile_editor() != 0:
            print("Failed to compile Unreal Editor.")
            sys.exit(1)


if __name__ == "__main__":
    main()
