import json
from uepyscripts import logger

def setup_parser(subparsers):
    parser = subparsers.add_parser("ubt", help="Execute RunUBT")
    parser.add_argument("arguments", type=str, help="JSON string representing an array of arguments to pass to RunUBT. Ex: ['item1', 'item2', 'item3']")
    parser.set_defaults(func=ubt)

def uat(args):
    logger.info(f"Command UBT called")

    arguments = json.loads(args.arguments) if args.arguments else []

    logger.info(f"Arguments : {arguments}")

    from uepyscripts import run
    run.ubt(arguments)