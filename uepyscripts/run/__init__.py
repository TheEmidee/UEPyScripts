from uepyscripts import logger
from uepyscripts.internal.engine import get_engine

def uat(args: list[str]):
    logger.info("UAT - {args}".format( args = args ))

    engine = get_engine()
    engine.uat( args )

def buildgraph(
    target: str, 
    extra_properties : dict[str,str] = None, 
    extra_parameters : list[str] = None
):
    logger.info(f"Run Buildgraph - Target : {target}")
    logger.debug(f"Extra Properties : {extra_properties}")
    logger.debug(f"Extra Parameters : {extra_parameters}")
    
    uat(["a","b"])