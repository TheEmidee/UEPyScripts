import sys

from uepyscripts.context import engine


def main() -> None:
    print("Starting Unreal Editor...")
    if engine.run_editor() != 0:
        print("Failed to start Unreal Editor.")
        sys.exit(1)


if __name__ == "__main__":
    main()
