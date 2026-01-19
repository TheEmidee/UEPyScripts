from uepyscripts.context import engine
from uepyscripts.context import project

engine.ubt([
    "-projectfiles", 
    f"-project={project.uproject_path}",
    "-game",
    "-rocket",
    "-progress" 
])