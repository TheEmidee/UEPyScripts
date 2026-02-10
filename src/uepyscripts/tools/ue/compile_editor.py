import sys

from uepyscripts.context import engine, project


def main() -> None:
    print("Compiling Unreal Editor...")
    if (
        engine.build(
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
