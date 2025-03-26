from uepyscripts import logger
from uepyscripts.context import engine
from uepyscripts.context import project
from uepyscripts.context import config
from pathlib import Path

def fix_path(path : Path) -> str:
    return str(path).replace("\\\\", "\\")

def uat(args: list[str]):
    engine.uat( args )

def ubt(args: list[str]):
    engine.ubt( args )

def buildgraph(
    target: str, 
    extra_properties : dict[str,str] = None, 
    extra_parameters : list[str] = None
    ):
    logger.info(f"Run Buildgraph - Target : {target}")
    logger.debug(f"Extra Properties : {extra_properties}")
    logger.debug(f"Extra Parameters : {extra_parameters}")

    if target == "":
        raise Exception("You must give a target to buildgraph")

    buildgraph_path = project.root_folder.joinpath(config["Project"]["BuildgraphPath"])
    logger.debug( f"Buildgraph XML path : {buildgraph_path}")

    if not buildgraph_path.exists():
        raise Exception(f"Impossible to get a valid path to the buildgraph XML file. Current path : {buildgraph_path}")

    extension = buildgraph_path.suffix
    if extension != ".xml":
        raise Exception(f"The buildgraph file must be a XML file. Current path : {buildgraph_path}")
    
    arguments = [ "BuildGraph" ]
    arguments.append(f"-script={buildgraph_path}")
    arguments.append(f"-target={target}")
    arguments.append(f"-Project={project.uproject_path}")

    automation_scripts_path = config["Project"]["AutomationScriptsDirectory"]
    if automation_scripts_path == "":
        logger.info("No automation scripts directory is set")
    else:
        automation_scripts_path = project.root_folder.joinpath(automation_scripts_path)
        if not automation_scripts_path.exists():
            raise Exception(f"The automation scripts directory does not exist. Current value {automation_scripts_path}")

        logger.info(f"Automation Scripts directory set to {automation_scripts_path}")        
        arguments.append(f"-ScriptDir={automation_scripts_path}")

    shared_properties = dict(pair.split('=') for pair in config["Project"]["BuildgraphSharedProperties"].split(','))

    if shared_properties is not None:
        for key, value in shared_properties.items():
            arguments.append(f"-set:{key}={value}")

    if extra_properties is not None:
        for key, value in extra_properties.items():
            arguments.append(f"-set:{key}={value}")

    if extra_parameters is not None:
        for arg in extra_parameters:
            arguments.append(arg)
    
    uat(arguments)