from .. import engine
from .. import logger

def run(
    target: str, 
    extra_properties : dict[str,str] = None, 
    extra_parameters : list[str] = None
):
    logger.info(f"Run Buildgraph - Target : {target}")
    logger.debug(f"Extra Properties : {extra_properties}")
    logger.debug(f"Extra Parameters : {extra_parameters}")
    
    engine.uat(["a","b"])