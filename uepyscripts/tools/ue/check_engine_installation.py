from ...tools.ue.engine_installation.engine_destination import resolve_engine_destination
from ...tools.ue.engine_installation.engine_source import resolve_engine_source
from ...internal.project import resolve_project
from ...internal.engine import resolve_engine
from ... import logger

try:
    project = resolve_project()
except Exception as e:
    logger.fatal(f"Project resolution failed: {e}")
    exit(1)

try:
    engine = resolve_engine(project)
except Exception as e:
    logger.error(f"Engine resolution failed: {e}")

    try:
        engine_source = resolve_engine_source(project)
        engine_destination = resolve_engine_destination(project)
        
        logger.info(f"Copy the engine from '{engine_source.source_file}' to '{engine_destination}'")

        engine_destination.mkdir(parents=True, exist_ok=True)        
        engine_source.copy_engine_to(engine_destination)
    except Exception as e:
        logger.fatal(f"Error when installing the engine: {e}")
        exit(1)