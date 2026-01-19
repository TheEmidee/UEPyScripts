from uepyscripts.context import engine, project

engine.ubt(["-projectfiles", f"-project={project.uproject_path}", "-game", "-rocket", "-progress"])
