import logging

logger = logging.getLogger("uepyscripts")
logger.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
console_handler.setFormatter(formatter)

logger.addHandler(console_handler)

# Ensure the logger doesn't propagate to the root logger
logger.propagate = False

try:
    from .internal.project import resolve_project
    from .internal.engine import resolve_engine
    
    project = resolve_project()
    engine = resolve_engine(project)
except Exception as e:
    logger.fatal(e)