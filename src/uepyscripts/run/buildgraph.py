import argparse
import re
from pathlib import Path
from typing import Any, Optional, Sequence

from pydantic import BaseModel, ConfigDict, field_validator

from .. import logger
from ..context import config, engine, project


class BuildgraphExecutionInfos(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True
        )

    target: str = ""
    properties: dict[str, str] = {}
    extra_arguments: list[str] = []

    @field_validator("properties", mode="before")
    @classmethod
    def parse_properties(cls, v: Any) -> dict[str, str]:  # noqa: ANN401
        if isinstance(v, str):
            import json
            v = json.loads(v)
            
        if isinstance(v, dict):
            return {str(key): str(value) for key, value in v.items()}
        raise ValueError("Properties must be a dictionary or JSON string")

    @field_validator("extra_arguments", mode="before")
    @classmethod
    def parse_extra_arguments(cls, v: Any) -> list[str]:  # noqa: ANN401
        if isinstance(v, str):
            import json
            v = json.loads(v)

        if isinstance(v, list):
            return [str(item) for item in v]
        raise ValueError("Extra arguments must be a list or JSON string")


def run(execution_infos: BuildgraphExecutionInfos) -> int:
    logger.info(f"Run Buildgraph - Target : {execution_infos.target}")
    logger.debug(f"Extra Properties : {execution_infos.properties}")
    logger.debug(f"Extra Parameters : {execution_infos.extra_arguments}")

    buildgraph_path = project.root_folder.joinpath(config["Project"]["BuildgraphPath"])
    logger.debug(f"Buildgraph XML path : {buildgraph_path}")

    if not buildgraph_path.exists():
        raise Exception(f"Impossible to get a valid path to the buildgraph XML file. Current path : {buildgraph_path}")

    extension = buildgraph_path.suffix
    if extension != ".xml":
        raise Exception(f"The buildgraph file must be a XML file. Current path : {buildgraph_path}")

    arguments = ["BuildGraph"]
    arguments.append(f'-script="{buildgraph_path}"')

    # We can execute buildgraph without a target if the SingleNode argument is set
    if execution_infos.target:
        arguments.append(f'-target="{execution_infos.target}"')

    arguments.append(f'-Project="{project.uproject_path}"')

    automation_scripts_directories = config["Project"]["AutomationScriptsDirectories"]
    if automation_scripts_directories == "" or automation_scripts_directories is None:
        logger.info("No automation scripts directory is set")
    else:
        automation_scripts_paths = automation_scripts_directories.split("+")

        for automation_scripts_path_str in automation_scripts_paths:
            automation_scripts_path = Path(automation_scripts_path_str)
            automation_scripts_path = project.root_folder.joinpath(automation_scripts_path)
            if not automation_scripts_path.exists():
                logger.warning(f"The automation scripts directory does not exist. Current value {automation_scripts_path}")
                continue

            logger.info(f"Automation Scripts directory set to {automation_scripts_path}")
            arguments.append(f"-ScriptDir={automation_scripts_path}")

    shared_properties = dict(pair.split("=") for pair in config["Project"]["BuildgraphSharedProperties"].split("+"))

    if shared_properties is not None:
        for key, value in shared_properties.items():
            arguments.append(f"-set:{key}={value}")

    if execution_infos.properties is not None:
        for key, value in execution_infos.properties.items():
            if " " in value:
                value = f'"{value}"'
            arguments.append(f"-set:{key}={value}")

    if execution_infos.extra_arguments is not None:
        for arg in execution_infos.extra_arguments:
            arguments.append(arg)
            
    return engine.uat(arguments)


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Execute a buildgraph task based on a target and properties.")
    parser.add_argument("--target", type=str, default="", help="The target to run in the buildgraph file")
    parser.add_argument(
        "--properties",
        type=str,
        default=None,
        nargs="?",
        help='JSON string representing a dictionary with the properties to pass to buildgraph. Ex: \'{"key1": "value1", "key2": "value2"}\'',
    )
    parser.add_argument(
        "--extra_arguments",
        type=str,
        default="",
        help='JSON string representing an array of extra arguments to pass to buildgraph. Ex: \'["item1", "item2", "item3"]\'',
    )
    parser.add_argument(
        "--string_arguments",
        type=str,
        default="",
        help='Space separated lists of arguments to pass as extra_arguments Ex: \'"item1" "item2" "item3"\'',
    )
    parser.add_argument("--config_file", type=str, default="", help="Path to a JSON file containing the target, properties, and extra arguments")
    return parser.parse_args(argv)


def validate_config(execution_infos: BuildgraphExecutionInfos) -> None:
    """Validate the configuration values."""
    pattern = r'-SingleNode="[^"]*"'

    if not execution_infos.target and not any(re.search(pattern, item) for item in execution_infos.extra_arguments):
        raise ValueError("Target is required")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_arguments(argv)

    execution_infos = BuildgraphExecutionInfos()

    if args.config_file:
        config_file_path = Path(args.config_file)
        if config_file_path.exists():
            with open(config_file_path, "r", encoding="utf-8") as f:
                json_str = f.read()
                execution_infos = BuildgraphExecutionInfos.model_validate_json(json_str)
        else:
            logger.warning(f"Config file not found at {config_file_path}")

    if args.target:
        execution_infos.target = args.target

    if args.properties:
        logger.debug(f"Properties from command line: {args.properties}")
        execution_infos.properties = args.properties

    if args.extra_arguments:
        logger.debug(f"Extra Arguments from command line: {args.extra_arguments}")
        execution_infos.extra_arguments = args.extra_arguments

    def split_string_arguments(string_arguments: str) -> list[str]:
        pattern = r'[^\s"]+="[^"]*"|[^\s"]+'
        return re.findall(pattern, string_arguments)

    # Split string arguments into a list. The regex captures quoted strings and unquoted words.
    # This allows for arguments like --arg="value with spaces" to be handled correctly
    string_arguments = split_string_arguments(args.string_arguments)
    execution_infos.extra_arguments += string_arguments

    try:
        validate_config(execution_infos)
    except (ValueError, TypeError) as e:
        logger.error(f"Configuration validation failed: {e}")
        raise e

    try:
        return run(execution_infos)
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        raise e


if __name__ == "__main__":
    main()
