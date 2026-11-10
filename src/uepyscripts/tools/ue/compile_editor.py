import argparse
import sys

from uepyscripts.internal.workspace import add_uproject_argument, open_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile the editor target of the project.")
    add_uproject_argument(parser)
    args = parser.parse_args()

    with open_workspace(args) as workspace:
        print("Compiling Unreal Editor...")
        if workspace.engine.compile_editor() != 0:
            print("Failed to compile Unreal Editor.")
            sys.exit(1)


if __name__ == "__main__":
    main()
