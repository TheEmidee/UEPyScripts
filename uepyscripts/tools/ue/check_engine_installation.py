"""
Check and install Unreal Engine installation for the given project.

If the required engine version can not be found, this script can copy an archive from:
* a local or a shared folder
* an AWS S3 bucket.
The destination folder can be defined through an environment variable, 
or from the config.ini file in the Config/PyScripts folder of the project.
When the archive is copied in the destination folder, the script will:
* extract the archive in-place
* delete the archive
* register the engine in the windows registry.

This script supports working in unattended mode to bypass the prompt to confirm the various actions, 
which is useful when executed on a build pipeline like Jenkins or Horde.
"""

import argparse

from ...tools.ue.engine_installation.engine_installer import EngineInstaller
from ...internal.project import resolve_project
from ...internal.engine import resolve_engine
from ... import logger

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description='Check and install Unreal Engine installation for the given project.'
    )
    parser.add_argument(
        '--unattended',
        action='store_true',
        help='Disable interactive prompts'
    )
    
    return parser.parse_args()

def main():
    """Main function."""
    args = parse_arguments()

    try:
        project = resolve_project()
    except Exception as e:
        logger.fatal(f"Project resolution failed: {e}")
        exit(1)

    try:
        engine = resolve_engine(project)
        logger.info(f"Engine '{engine.version}' for project '{project.project_name}' is already installed at '{engine.root_path}'. No action is required.")
    except Exception as e:
        logger.error(f"Engine resolution failed: {e}")

        try:
            engine_installer = EngineInstaller(project)
            task_list = engine_installer.get_task_list()
            task_list.print()

            if not args.unattended:
                while True:
                    prompt = (
    "╔═══════════════════════════════════════════════════╗\n"
    "║  Are you OK to proceed with the above operations? ║\n"
    "╚═══════════════════════════════════════════════════╝\n"
    "Enter Y or N: "
)
                    response = input(prompt).strip().upper()
                    if response in ['Y', 'N']:
                        break
                    print("Please enter Y or N")
            
            if response == 'N':
                exit(0)

            task_list.execute()

            logger.info(f"Engine installation completed successfully.")
        except Exception as e:
            logger.fatal(f"Error when installing the engine: {e}")
            exit(1)

if __name__ == '__main__':
    main()