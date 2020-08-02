from io import StringIO
import os
from threading import Event
from typing import Any, List, Optional, TextIO

from austin.stats import AustinStats, InvalidSample, Sample
from austin.threads import ThreadedAustin
from psutil import Process


class PyTestAustin(ThreadedAustin):
    """pytest implementation of Austin."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.ready = Event()
        self.stats = AustinStats()
        self.interval: str = "100"
        self.children = False
        self.mode: Optional[str] = None
        self.data: List[str] = []
        self.global_stats: Optional[str] = None

    def on_ready(
        self, process: Process, child_process: Process, command_line: str
    ) -> None:
        """Ready callback."""
        self.ready.set()

    def on_sample_received(self, sample: str) -> None:
        """Sample received callback."""
        # We collect all the samples and only parse them at the end for
        # performance
        self.data.append(sample)

    def on_terminate(self, stats: str) -> None:
        """Terminate callback."""
        self.global_stats = stats
        self.ready.set()

    def wait_ready(self, timeout: Optional[int] = None):
        """Wait for Austin to enter the ready state."""
        self.ready.wait(timeout)

    def dump(self, stream: TextIO) -> None:
        """Dump the collected statistics to the given IO stream."""
        if not self.data:
            return

        for sample in self.data:
            try:
                self.stats.update(Sample.parse(sample))
            except InvalidSample:
                pass

        if self.mode != "-f":
            buffer = StringIO()
            self.stats.dump(buffer)
            stream.write(buffer.getvalue().replace(" 0 0", ""))
        else:
            self.stats.dump(stream)

    def start(self) -> None:
        """Start Austin."""
        args = ["-t", "1", "-i", self.interval, "-p", str(os.getpid())]
        if self.mode:
            args.append(self.mode)
        if self.children:
            args.append("-C")

        super().start(args)
