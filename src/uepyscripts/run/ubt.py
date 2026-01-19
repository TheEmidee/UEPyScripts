import argparse
import json

from uepyscripts.context import engine

parser = argparse.ArgumentParser(description="Execute different tasks based on command-line arguments.")
parser.add_argument("--arguments", type=str, default="", help="JSON string representing an array of extra arguments to pass to UBT. Ex: ['item1', 'item2', 'item3']")
args = parser.parse_args()

arguments = json.loads(args.arguments) if args.arguments else {}

engine.ubt( arguments )