import argparse

from uepyscripts.context import engine


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute different tasks based on command-line arguments.")
    parser.add_argument("arguments", nargs="*", help="Extra arguments to pass to UBT")

    args: argparse.Namespace = parser.parse_args()

    arguments: list[str] = args.arguments

    return engine.ubt(arguments)


if __name__ == "__main__":
    main()
