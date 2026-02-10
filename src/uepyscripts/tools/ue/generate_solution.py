import sys

from uepyscripts.context import engine, project


def main() -> None:
    if engine.ubt(["-projectfiles", f"-project={project.uproject_path}", "-game", "-rocket", "-progress"]) != 0:
        print("Failed to generate project files.")
        sys.exit(1)


if __name__ == "__main__":
    main()
