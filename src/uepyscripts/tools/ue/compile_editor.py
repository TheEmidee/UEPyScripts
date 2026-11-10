import argparse
import sys

from uepyscripts.internal.workspace import add_uproject_argument, open_workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile the editor target of the project.")
    add_uproject_argument(parser)
    args = parser.parse_args()

    with open_workspace(args) as workspace:
        project = workspace.project
        print("Compiling Unreal Editor...")
        if (
            workspace.engine.build(
                [
                    f"{project.project_name}Editor",
                    "Win64",
                    "Development",
                    f"-project={project.uproject_path}",
                    "-WaitMutex",
                    "-FromMsBuild",
                    f"-log={project.root_folder}/Saved/Logs/Compile_Editor_Development_Win64.log",
                ]
            )
            != 0
        ):
            print("Failed to compile Unreal Editor.")
            sys.exit(1)


if __name__ == "__main__":
    main()
