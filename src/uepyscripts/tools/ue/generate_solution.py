from uepyscripts.context import engine, project


def main() -> int:
    return engine.ubt(["-projectfiles", f"-project={project.uproject_path}", "-game", "-rocket", "-progress"])


if __name__ == "__main__":
    main()
