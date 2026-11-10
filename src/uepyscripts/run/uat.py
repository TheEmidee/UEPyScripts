import argparse

from uepyscripts.internal.workspace import add_uproject_argument, open_workspace


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run UAT. Every argument except --uproject-path is forwarded to UAT.", allow_abbrev=False, add_help=False
    )
    add_uproject_argument(parser)

    args, forwarded_arguments = parser.parse_known_args()

    with open_workspace(args) as workspace:
        return workspace.engine.uat(forwarded_arguments)


if __name__ == "__main__":
    main()
