import pytest

from uepyscripts import logger


@pytest.fixture(autouse=True)
def route_logs_through_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    """The package logger writes straight to the console and doesn't propagate,
    which bypasses pytest's log capture. Send records to pytest instead, so
    they only show up for failing tests (and in caplog)."""
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "propagate", True)
