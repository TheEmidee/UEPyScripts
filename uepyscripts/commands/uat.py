import argparse

def setup_parser(subparsers):
    parser = subparsers.add_parser("uat", help="Execute function one")
    parser.add_argument("arg1", type=str, help="Argument for function one")
    parser.set_defaults(func=uat)

def uat(args):
    print(f"Function One called with argument: {args.arg1}")