from uepyscripts.context import engine
from uepyscripts.context import project

engine.build([
    f"{project.project_name}Editor",
    "Win64",
    "Development",
    f"-project={project.uproject_path}",
    "-WaitMutex",
    "-FromMsBuild",
    f"-log={project.root_folder}/Saved/Logs/Compile_Editor_Development_Win64.log"
])