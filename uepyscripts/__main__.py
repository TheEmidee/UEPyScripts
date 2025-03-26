import argparse
import os
import importlib.util

from uepyscripts import logger

def main():
    parser = argparse.ArgumentParser(description="Execute different tasks based on command-line arguments.")
    subparsers = parser.add_subparsers(dest="command", help="Sub-command help")

    current_dir = os.path.dirname(os.path.abspath(__file__))
    scripts_dir = os.path.join(current_dir, "commands")

    logger.debug( f"Parsing commands modules in {scripts_dir}")

    for filename in os.listdir(scripts_dir):
        if filename.endswith(".py"):
            module_name = filename[:-3]  # Remove the .py extension
            module_path = os.path.join(scripts_dir, filename)

            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            if hasattr(module, "setup_parser"):
                logger.debug( f"Setup parse for command {module_name}")
                module.setup_parser(subparsers)

    args = parser.parse_args()

    if args.command:
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()