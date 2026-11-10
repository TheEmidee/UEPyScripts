import argparse
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from uepyscripts.run import uat, ubt


class RecordingEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def uat(self, args: list[str]) -> int:
        self.calls.append(("uat", args))
        return 7

    def ubt(self, args: list[str]) -> int:
        self.calls.append(("ubt", args))
        return 7


def run_main(module: ModuleType, argv: list[str], monkeypatch: pytest.MonkeyPatch) -> tuple[int, RecordingEngine, argparse.Namespace]:
    engine = RecordingEngine()
    opened: list[argparse.Namespace] = []

    @contextmanager
    def fake_open_workspace(args: argparse.Namespace) -> Iterator[SimpleNamespace]:
        opened.append(args)
        yield SimpleNamespace(engine=engine)

    monkeypatch.setattr(module, "open_workspace", fake_open_workspace)
    monkeypatch.setattr("sys.argv", [f"ue-run-{module.__name__.rsplit('.', 1)[-1]}", *argv])

    exit_code = module.main()
    return exit_code, engine, opened[0]


@pytest.mark.parametrize("module", [uat, ubt])
@pytest.mark.parametrize("help_flag", ["-help", "-h", "--help", "-hotreload"])
def test_help_like_arguments_are_forwarded(module: ModuleType, help_flag: str, monkeypatch: pytest.MonkeyPatch) -> None:
    exit_code, engine, _ = run_main(module, [help_flag], monkeypatch)

    assert exit_code == 7
    assert engine.calls == [(module.__name__.rsplit(".", 1)[-1], [help_flag])]


@pytest.mark.parametrize("module", [uat, ubt])
def test_uproject_path_is_consumed_and_the_rest_forwarded_in_order(module: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    _, engine, args = run_main(module, ["turnkey", "--uproject-path", "Game.uproject", "-command=VerifySdk", "-help"], monkeypatch)

    assert args.uproject_path == Path("Game.uproject")
    assert engine.calls[0][1] == ["turnkey", "-command=VerifySdk", "-help"]
