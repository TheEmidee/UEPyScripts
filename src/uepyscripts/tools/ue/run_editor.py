import argparse
import sys

from uepyscripts.internal.workspace import add_uproject_argument, open_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the Unreal Editor for the project.")
    add_uproject_argument(parser)
    args = parser.parse_args()

    with open_workspace(args) as workspace:
        print("Starting Unreal Editor...")
        if workspace.engine.run_editor() != 0:
            print("Failed to start Unreal Editor.")
            sys.exit(1)


if __name__ == "__main__":
    main()
