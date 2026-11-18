import argparse
import sys
from typing import Optional, Sequence

from uepyscripts.internal.process import ProcessRunner
from uepyscripts.internal.workspace import add_uproject_argument, open_workspace


def main(argv: Optional[Sequence[str]] = None, *, runner: Optional[ProcessRunner] = None) -> None:
    parser = argparse.ArgumentParser(description="Generate the Visual Studio solution for the project.")
    add_uproject_argument(parser)
    args = parser.parse_args(argv)

    with open_workspace(args, runner=runner) as workspace:
        if workspace.engine.generate_project_files() != 0:
            print("Failed to generate project files.")
            sys.exit(1)


if __name__ == "__main__":
    main()
