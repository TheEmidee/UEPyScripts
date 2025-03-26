import json
from uepyscripts import logger

def setup_parser(subparsers):
    parser = subparsers.add_parser("buildgraph", help="Execute the buildgraph commandlet")
    parser.add_argument("target", type=str, help="The target to run in the buildgraph file")
    parser.add_argument("--properties", type=str, default="", help="JSON string representing a dictionary with the properties to pass to buildgraph. Ex: {'key1': 'value1', 'key2': 'value2'}")
    parser.add_argument("--extra_arguments", type=str, default="", help="JSON string representing an array of extra arguments to pass to builgraph. Ex: ['item1', 'item2', 'item3']")
    parser.set_defaults(func=buildgraph)

def buildgraph(args):
    logger.info(f"Command BuildGraph called")
    logger.info(f"Target Name : {args.target}")

    properties = json.loads(args.properties) if args.properties else {}
    extra_arguments = json.loads(args.extra_arguments) if args.extra_arguments else []

    logger.info(f"Properties : {properties}")
    logger.info(f"Extra Arguments : {extra_arguments}")

    from uepyscripts import run
    run.buildgraph( args.target, properties, extra_arguments )