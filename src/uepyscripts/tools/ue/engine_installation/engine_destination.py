from pathlib import Path

from .... import logger
from ....internal.project import Project
from ....tools.helpers import get_env_var_value


def resolve_engine_destination(project: Project) -> Path:
    logger.info("Resolving engine destination...")

    logger.info("Try to use the environment variable")
    env_var_value = get_env_var_value()
    if env_var_value:
        destination = Path(env_var_value)
        destination = destination.joinpath(project.engine_association)
        logger.info(f"Using engine destination from environment variable at '{destination}'")
        return destination

    raise FileNotFoundError("No engine destination could be resolved")
