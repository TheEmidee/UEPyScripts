import argparse
import json

from uepyscripts import logger
from uepyscripts.context import engine
from uepyscripts.context import project
from uepyscripts.context import config

def run(
    target: str,
    properties: dict[str,str],
    extra_arguments: list[str]
    ):

    logger.info(f"Run Buildgraph - Target : {target}")
    logger.debug(f"Extra Properties : {properties}")
    logger.debug(f"Extra Parameters : {extra_arguments}")

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
    arguments.append(f"-script=\"{buildgraph_path}\"")
    arguments.append(f"-target=\"{target}\"")
    arguments.append(f"-Project=\"{project.uproject_path}\"")

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

    if properties is not None:
        for key, value in properties.items():
            arguments.append(f"-set:{key}={value}")

    if extra_arguments is not None:
        for arg in extra_arguments:
            arguments.append(arg)

    engine.uat( arguments )

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Execute different tasks based on command-line arguments.")
    parser.add_argument("target", type=str, help="The target to run in the buildgraph file")
    parser.add_argument("--properties", type=str, default="", help="JSON string representing a dictionary with the properties to pass to buildgraph. Ex: {'key1': 'value1', 'key2': 'value2'}")
    parser.add_argument("--extra_arguments", type=str, default="", help="JSON string representing an array of extra arguments to pass to builgraph. Ex: ['item1', 'item2', 'item3']")
    args = parser.parse_args()

    target = args.target

    properties = json.loads(args.properties) if args.properties else {}
    extra_arguments = json.loads(args.extra_arguments) if args.extra_arguments else []

    run( target, properties, extra_arguments )