import io
import logging
import threading
from collections.abc import Iterator

import pytest

from uepyscripts import logger
from uepyscripts.tools.ugs.progress import TransferProgress


@pytest.fixture
def logged(caplog: pytest.LogCaptureFixture) -> Iterator[pytest.LogCaptureFixture]:
    logger.addHandler(caplog.handler)
    caplog.set_level(logging.INFO, logger=logger.name)
    yield caplog
    logger.removeHandler(caplog.handler)


def messages(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [record.getMessage() for record in caplog.records]


def test_outside_a_terminal_the_count_is_logged_every_ten_percent_and_at_the_end(logged: pytest.LogCaptureFixture) -> None:
    stream = io.StringIO()
    with TransferProgress("Uploading", 25, stream=stream, interactive=False) as progress:
        for _ in range(25):
            progress.advance()

    assert messages(logged) == [
        "Uploading file 1/25",
        "Uploading file 3/25",
        "Uploading file 5/25",
        "Uploading file 8/25",
        "Uploading file 10/25",
        "Uploading file 13/25",
        "Uploading file 15/25",
        "Uploading file 18/25",
        "Uploading file 20/25",
        "Uploading file 23/25",
        "Uploading file 25/25",
    ]
    assert stream.getvalue() == ""


def test_on_a_terminal_a_bar_shows_the_count_and_nothing_is_logged(logged: pytest.LogCaptureFixture) -> None:
    stream = io.StringIO()
    with TransferProgress("Downloading", 3, stream=stream, interactive=True) as progress:
        for _ in range(3):
            progress.advance()

    assert "Downloading file 3/3" in stream.getvalue()
    assert "100%" in stream.getvalue()
    assert messages(logged) == []


def test_advancing_from_several_threads_counts_every_file(logged: pytest.LogCaptureFixture) -> None:
    with TransferProgress("Uploading", 400, stream=io.StringIO(), interactive=False) as progress:

        def advance_100() -> None:
            for _ in range(100):
                progress.advance()

        threads = [threading.Thread(target=advance_100) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    assert messages(logged)[-1] == "Uploading file 400/400"


def test_nothing_to_transfer_shows_nothing(logged: pytest.LogCaptureFixture) -> None:
    stream = io.StringIO()
    with TransferProgress("Uploading", 0, stream=stream, interactive=True):
        pass

    assert stream.getvalue() == ""
    assert messages(logged) == []
