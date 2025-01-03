from .. import logger
from .project import Project

class Engine:
    def uat(self, args: list[str]):
        logger.info(f"UAT - {args}")

def resolve_engine(project: Project) -> Engine:
    return Engine()