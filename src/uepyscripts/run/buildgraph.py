import argparse
import re
from pathlib import Path
from typing import Optional, Sequence

from .. import logger
from ..internal.workspace import Workspace, add_uproject_argument, open_workspace


def run(workspace: Workspace, target: str, arguments: list[str], script: Optional[str] = None) -> int:
    logger.info(f"Run Buildgraph - Target : {target}")
    logger.info(f"Arguments : {arguments}")

    project = workspace.project
    config = workspace.config

    if script:
        buildgraph_path = Path(script)
    else:
        buildgraph_path = project.root_folder.joinpath(config["Project"]["BuildgraphPath"])
    logger.info(f"Buildgraph XML path : {buildgraph_path}")

    if not buildgraph_path.exists():
        raise Exception(f"Impossible to get a valid path to the buildgraph XML file. Current path : {buildgraph_path}")

    extension = buildgraph_path.suffix
    if extension != ".xml":
        raise Exception(f"The buildgraph file must be a XML file. Current path : {buildgraph_path}")

    uat_arguments = ["BuildGraph"]
    uat_arguments.append(f"-script={buildgraph_path}")

    # We can execute buildgraph without a target if the SingleNode argument is set
    if target != "":
        uat_arguments.append(f"-target={target}")

    uat_arguments.append(f"-Project={project.uproject_path}")

    if config.valid:
        automation_scripts_directories = config["Project"].get("AutomationScriptsDirectories")
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
                uat_arguments.append(f"-ScriptDir={automation_scripts_path}")

        shared_properties_str = config["Project"].get("BuildgraphSharedProperties", "")
        if shared_properties_str == "" or shared_properties_str is None:
            logger.info("No shared properties to set")
        else:
            shared_properties = dict(pair.split("=") for pair in shared_properties_str.split("+")) if shared_properties_str else {}

            if shared_properties is not None:
                for key, value in shared_properties.items():
                    uat_arguments.append(f"-set:{key}={value}")

    for arg in arguments:
        uat_arguments.append(arg)

    return workspace.engine.uat(uat_arguments)


def parse_arguments(argv: Optional[Sequence[str]] = None) -> tuple[argparse.Namespace, list[str]]:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Execute a buildgraph task based on a target and properties.")
    parser.add_argument("--target", type=str, default="", help="The target to run in the buildgraph file")
    parser.add_argument(
        "--script", type=str, default=None, help="Path to the buildgraph XML file. If not set, resolved from the project configuration."
    )
    add_uproject_argument(parser)
    return parser.parse_known_args(argv)


def validate_config(target: str, arguments: list[str], script: Optional[str], uproject_path: Optional[Path]) -> None:
    """Validate the configuration values."""
    pattern = r'-SingleNode=[^"]*'

    if not target and not any(re.search(pattern, item) for item in arguments):
        raise ValueError("Target is required")

    if script and not uproject_path:
        raise ValueError("--uproject-path is required when --script is set")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args, other_arguments = parse_arguments(argv)

    target = ""

    if args.target:
        target = args.target

    try:
        logger.info("Validating configuration")
        validate_config(target, other_arguments, args.script, args.uproject_path)
    except (ValueError, TypeError) as e:
        logger.error(f"Configuration validation failed: {e}")
        raise e

    with open_workspace(args) as workspace:
        try:
            return run(workspace, target, other_arguments, args.script)
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            raise e


if __name__ == "__main__":
    main()
