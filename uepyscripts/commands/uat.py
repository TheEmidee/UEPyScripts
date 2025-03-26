import json
from uepyscripts import logger

def setup_parser(subparsers):
    parser = subparsers.add_parser("uat", help="Execute RunUAT")
    parser.add_argument("arguments", type=str, help="JSON string representing an array of arguments to pass to RunUAT. Ex: ['item1', 'item2', 'item3']")
    parser.set_defaults(func=uat)

def uat(args):
    logger.info(f"Command UAT called")

    arguments = json.loads(args.arguments) if args.arguments else []

    logger.info(f"Arguments : {arguments}")

    from uepyscripts import run
    run.uat(arguments)