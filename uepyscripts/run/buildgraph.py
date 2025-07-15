import argparse
import json

from pathlib import Path
from typing import Any, Dict, List
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

    if engine.uat( arguments ) != 0:
        raise RuntimeError("Error while running UAT")
    
def load_config_from_file(config_file_path: Path) -> Dict[str, Any]:
    """Load configuration from JSON file."""
    try:
        with open(config_file_path, 'r') as config_file:
            config_data = json.load(config_file)
            logger.debug(f"Config loaded from {config_file_path}")
            return config_data
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.error(f"Failed to load config file {config_file_path}: {e}")
        raise

def parse_json_argument(arg_value: str, arg_name: str, default_value: Any) -> Any:
    """Parse JSON string argument with error handling."""
    if not arg_value:
        return default_value

    try:
        return json.loads(arg_value)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in {arg_name}: {e}")
        raise argparse.ArgumentTypeError(f"Invalid JSON format in {arg_name}: {e}")

def extract_config_values(config_data: Dict[str, Any]) -> tuple[str, Dict[str, str], List[str]]:
    """Extract target, properties, and extra_arguments from config data."""
    target = config_data.get('Target', '')
    
    properties_raw = config_data.get('Properties', {})
    if isinstance(properties_raw, str):
        properties = parse_json_argument(properties_raw, 'Properties', {})
    else:
        properties = properties_raw
    
    extra_args_raw = config_data.get('ExtraArguments', [])
    if isinstance(extra_args_raw, str):
        extra_arguments = parse_json_argument(extra_args_raw, 'ExtraArguments', [])
    else:
        extra_arguments = extra_args_raw
    
    return target, properties, extra_arguments

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Execute different tasks based on command-line arguments."
    )
    parser.add_argument(
        "--target", 
        type=str, 
        help="The target to run in the buildgraph file"
    )
    parser.add_argument(
        "--properties", 
        type=str, 
        default="", 
        help="JSON string representing a dictionary with the properties to pass to buildgraph. "
             "Ex: '{\"key1\": \"value1\", \"key2\": \"value2\"}'"
    )
    parser.add_argument(
        "--extra_arguments", 
        type=str, 
        default="", 
        help="JSON string representing an array of extra arguments to pass to buildgraph. "
             "Ex: '[\"item1\", \"item2\", \"item3\"]'"
    )
    parser.add_argument(
        "--string_arguments", 
        type=str, 
        default="", 
        help="Space separated lists of arguments to pass as extra_argumentsJSON string representing an array of extra arguments to pass to buildgraph. "
             "Ex: '\"item1\" \"item2\" \"item3\"'"
    )
    parser.add_argument(
        "--config_file", 
        type=str, 
        default="", 
        help="Path to a JSON file containing the target, properties, and extra arguments"
    )
    return parser.parse_args()

def validate_config(target: str, properties: Dict[str, str], extra_arguments: List[str]) -> None:
    """Validate the configuration values."""
    if not target:
        raise ValueError("Target is required")
    
    if not isinstance(properties, dict):
        raise TypeError("Properties must be a dictionary")
    
    if not isinstance(extra_arguments, list):
        raise TypeError("Extra arguments must be a list")


if __name__ == '__main__':
    args = parse_arguments()
    
    target = ""
    properties = {}
    extra_arguments = []

    if args.config_file:
        config_file_path = Path(args.config_file)
        if config_file_path.exists():
            config_data = load_config_from_file(config_file_path)
            target, properties, extra_arguments = extract_config_values(config_data)
        else:
            logger.warning(f"Config file not found at {config_file_path}")

    if args.target:
        target = args.target
    
    if args.properties:
        logger.debug(f"Properties from command line: {args.properties}")
        properties = parse_json_argument(args.properties, 'properties', {})
    
    if args.extra_arguments:
        logger.debug(f"Extra Arguments from command line: {args.extra_arguments}")
        extra_arguments = parse_json_argument(args.extra_arguments, 'extra_arguments', [])

    string_arguments = args.string_arguments.split()
    extra_arguments += string_arguments

    try:
        validate_config(target, properties, extra_arguments)
    except (ValueError, TypeError) as e:
        logger.error(f"Configuration validation failed: {e}")
        raise e
    
    logger.info(f"Running target: {target}")
    logger.debug(f"Properties: {properties}")
    logger.debug(f"Extra arguments: {extra_arguments}")

    try:
        run(target, properties, extra_arguments)
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        raise e