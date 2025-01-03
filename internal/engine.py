from .. import logger
from .project import Project
from pathlib import Path
import os

class Engine:
    root_path : Path
    path : Path
    version : str

    def __init__(self, root_path:Path):
        self.root_path = root_path
        self.path = Path(root_path).joinpath("Engine")

    def uat(self, args: list[str]):
        logger.info(f"UAT - {args}")

    def __str__(self):
        return f"""
----- Engine infos -----
* Path : {self.path}
----- Engine infos -----
        """

def resolve_engine_path(project: Project) -> str:
    return os.path.realpath(__file__)

def resolve_engine(project: Project) -> Engine:
    engine = Engine(resolve_engine_path(project))
    logger.info(engine)
    return engine