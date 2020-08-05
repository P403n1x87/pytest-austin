from datetime import timedelta as td
from functools import lru_cache
from io import StringIO
import os
from threading import Event
from time import time
from typing import Any, Dict, Iterator, List, Optional, TextIO

from austin.stats import AustinStats, Frame, FrameStats, InvalidSample, Sample
from austin.threads import ThreadedAustin
from psutil import Process


Microseconds = int


def _find_from_hierarchy(
    collector: List[FrameStats],
    stats_list: Dict[Frame, FrameStats],
    function: str,
    module: str,
) -> None:
    for label, stats in stats_list.items():
        if label.function == function and label.filename.endswith(module):
            collector.append(stats)
        else:
            _find_from_hierarchy(collector, stats.children, function, module)


def _parse_time(timedelta: Any, total_test_time: Microseconds) -> Microseconds:
    if isinstance(timedelta, td):
        return timedelta.total_seconds() * 1e6
    if isinstance(timedelta, str):
        perc = timedelta.strip()
        if not perc[-1] == "%":
            raise ValueError("Invalid % total time")
        return float(perc[:-1]) / 100 * total_test_time
    if isinstance(timedelta, float) or isinstance(timedelta, int):
        return timedelta

    raise ValueError(f"Invalid time delta type {type(timedelta)}")


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
        self.austinfile = None
        self.tests = {}
        self.report = []

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

    def dump(self, stream: Optional[TextIO] = None) -> None:
        """Dump the collected statistics to the given IO stream.

        If no stream is given, the data is dumped into a file prefixed with
        ``.austin_`` and followed by a truncated timestamp within the pytest
        rootdir.
        """
        if not self.data:
            return

        for sample in self.data:
            try:
                self.stats.update(Sample.parse(sample))
            except InvalidSample:
                pass

        def _dump(stream: TextIO) -> None:
            if self.mode != "-f":
                buffer = StringIO()
                self.stats.dump(buffer)
                stream.write(buffer.getvalue().replace(" 0 0", ""))
            else:
                self.stats.dump(stream)

        if stream is None:
            filename = f".austin_{int((time() * 1e6) % 1e14)}"
            with open(filename, "w") as fout:
                _dump(fout)
                self.austinfile = os.path.join(os.getcwd(), filename)
        else:
            _dump(stream)

    @lru_cache()
    def _index(self) -> Dict[str, Dict[str, FrameStats]]:
        # TODO: This code can be optimised. If we collect all the test items we
        # can index up to the test functions. Then we keep indexing whenever
        # we are checking eaech marked test.

        def _add_child_stats(
            stats: FrameStats, index: Dict[str, Dict[str, FrameStats]]
        ) -> None:
            """Build an index of all the functions in all the modules recursively."""
            for frame, stats in stats.children.items():
                index.setdefault(frame.function, {}).setdefault(
                    frame.filename, []
                ).append(stats)

                _add_child_stats(stats, index)

        index = {}

        for _, process in self.stats.processes.items():
            for _, thread in process.threads.items():
                _add_child_stats(thread, index)

        return index

    def register_test(self, function: str, module: str, markers: Iterator) -> None:
        """Register a test with pytest-austin.

        We pass the test item name and module together with any markers.
        """
        for marker in markers:
            self.tests.setdefault(function, {}).setdefault(module, []).append(marker)

    def _find_test(self, function: str, module: str) -> Optional[FrameStats]:
        # We expect to find at most one test
        # TODO: Match function by regex
        module_map = self._index().get(function, None)
        if module_map is None:
            return None

        matches = [module_map[k] for k in module_map if k.endswith(module)] + [None]
        if len(matches) > 2:
            RuntimeError(f"Test item {function} occurs in many matching modules.")

        return matches[0]

    def check_tests(self) -> int:
        """Check all the registered tests against the collected statistics.

        Returns the number of failed checks.
        """
        if self.is_running():
            raise RuntimeError("Austin is still running.")

        for function, modules in self.tests.items():
            for module, markers in modules.items():
                test_stats = self._find_test(function, module)
                if test_stats is None:
                    # The test was not found. Either there is no such test or
                    # Austin did not collect any statistics for it.
                    continue

                total_test_time = sum(fs.total.time for fs in test_stats)

                for marker in markers:
                    args = {"function": function, "module": module, "line": 0}
                    args.update(marker.kwargs)
                    args.update(
                        {
                            k: v
                            for k, v in zip(
                                ["time", "function", "module", "line"], marker.args
                            )
                        }
                    )

                    # find by function and module from index
                    function_stats = []
                    _find_from_hierarchy(
                        function_stats,
                        {s.label: s for s in test_stats},
                        args["function"],
                        args["module"],
                    )

                    if args["line"]:
                        function_stats = [
                            fs for fs in function_stats if fs.label.line == args["line"]
                        ]

                    function_total_time = sum(fs.total.time for fs in function_stats)

                    expected_time = _parse_time(args["time"], total_test_time)
                    outcome = function_total_time <= expected_time
                    if not outcome:
                        self.report.append(
                            (
                                function,
                                module,
                                args,
                                total_test_time,
                                function_total_time,
                                expected_time,
                                outcome,
                            )
                        )

        return len(self.report)

    def start(self) -> None:
        """Start Austin."""
        args = ["-t", "10", "-i", self.interval, "-p", str(os.getpid())]
        if self.mode:
            args.append(self.mode)
        if self.children:
            args.append("-C")

        super().start(args)
