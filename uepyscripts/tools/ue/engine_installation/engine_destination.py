import os
from pathlib import Path

from .... import logger
from ....internal.config import resolve_config
from ....internal.project import Project
from ....tools.helpers import get_env_var_value

def resolve_engine_destination(project: Project) -> Path:
    config = resolve_config(project)
    
    logger.info("Resolving engine destination...")

    logger.info("Try to use the environment variable")    
    destination = get_env_var_value()
    if destination:
        destination = Path(destination)
        destination = destination.joinpath(project.engine_association)
        logger.info(f"Using engine destination from environment variable at '{destination}'")
        return destination
    
    logger.info("Try to use [EngineDestination][DestinationFolder] from the config file")
    destination = Path(config["EngineDestination"]["DestinationFolder"])
    if destination:
        destination = destination.joinpath(project.engine_association)
        logger.info(f"Using engine destination from config file at '{destination}'")
        return destination
    
    raise FileNotFoundError("No engine destination could be resolved")
