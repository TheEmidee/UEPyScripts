"""
Progress of a batch of transfers with the Publish store: "Uploading file x/y".

On a terminal, a progress bar is drawn and redrawn in place. Anywhere else
(a CI log, a redirected output), redrawing would flood the log, so the same
text is logged once every `LOG_STEP_PERCENT` percent instead, and once at the
end. `advance` can be called from several threads at once.
"""

import sys
import threading
from types import TracebackType
from typing import Never, TextIO

from tqdm import tqdm

from uepyscripts import logger

LOG_STEP_PERCENT = 10


class TransferProgress:
    def __init__(self, verb: str, total: int, stream: TextIO | None = None, interactive: bool | None = None) -> None:
        """`verb` starts the text ("Uploading", "Downloading"). `stream` defaults
        to stderr, and `interactive` to whether it is a terminal."""
        self._verb = verb
        self._total = total
        self._done = 0
        self._next_log = 0
        self._lock = threading.Lock()
        stream = stream if stream is not None else sys.stderr
        interactive = interactive if interactive is not None else stream.isatty()

        self._bar: tqdm[Never] | None = None
        if interactive and total > 0:
            self._bar = tqdm(
                total=total,
                file=stream,
                bar_format=f"{verb} file {{n_fmt}}/{{total_fmt}} {{bar}} {{percentage:3.0f}}% [{{elapsed}}<{{remaining}}]",
                dynamic_ncols=True,
            )

    def advance(self) -> None:
        """One more file is done."""
        with self._lock:
            self._done += 1
            if self._bar is not None:
                self._bar.update(1)
            elif self._done * 100 >= self._next_log * self._total or self._done == self._total:
                logger.info(f"{self._verb} file {self._done}/{self._total}")
                self._next_log = self._done * 100 // self._total // LOG_STEP_PERCENT * LOG_STEP_PERCENT + LOG_STEP_PERCENT

    def close(self) -> None:
        if self._bar is not None:
            self._bar.close()

    def __enter__(self) -> "TransferProgress":
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None) -> None:
        self.close()
