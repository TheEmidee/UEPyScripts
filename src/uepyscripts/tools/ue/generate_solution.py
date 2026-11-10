import argparse
import sys

from uepyscripts.internal.workspace import add_uproject_argument, open_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Visual Studio solution for the project.")
    add_uproject_argument(parser)
    args = parser.parse_args()

    with open_workspace(args) as workspace:
        project = workspace.project
        if workspace.engine.ubt(["-projectfiles", f"-project={project.uproject_path}", "-game", "-rocket", "-progress"]) != 0:
            print("Failed to generate project files.")
            sys.exit(1)


if __name__ == "__main__":
    main()
