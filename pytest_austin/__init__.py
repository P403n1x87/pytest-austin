from datetime import timedelta as td
from functools import lru_cache
import os
from threading import Event
from time import time
from typing import Any, Dict, Iterator, List, Optional, TextIO

from austin.format.pprof import PProf
from austin.format.speedscope import Speedscope
from austin.stats import AustinStats, Frame, FrameStats, InvalidSample, Sample
from austin.threads import ThreadedAustin
from psutil import Process
import pytest_austin.markers as _markers


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
        self.report_level = "minimal"
        self.format = "austin"

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

        def _dump(filename, stream, dumper):
            if stream is None:
                with open(
                    filename, "wb" if filename.endswith("pprof") else "w"
                ) as fout:
                    dumper.dump(fout)
                    self.austinfile = os.path.join(os.getcwd(), filename)
            else:
                dumper.dump(stream)

        def _dump_austin():
            _dump(f".austin_{int((time() * 1e6) % 1e14)}.aprof", stream, self.stats)

        def _dump_pprof():
            pprof = PProf()

            for line in self.data:
                try:
                    pprof.add_sample(Sample.parse(line))
                except InvalidSample:
                    continue

            _dump(f".austin_{int((time() * 1e6) % 1e14)}.pprof", stream, pprof)

        def _dump_speedscope():
            name = f"austin_{int((time() * 1e6) % 1e14)}"
            speedscope = Speedscope(name)

            for line in self.data:
                try:
                    speedscope.add_sample(Sample.parse(line))
                except InvalidSample:
                    continue

            _dump(f".{name}.json", stream, speedscope)

        {"austin": _dump_austin, "pprof": _dump_pprof, "speedscope": _dump_speedscope}[
            self.format
        ]()

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
            try:
                marker_function = getattr(_markers, marker.name)
            except AttributeError:
                continue

            arg_names = marker_function.__code__.co_varnames[
                1 : marker_function.__code__.co_argcount
            ]
            defaults = marker_function.__defaults__ or []

            marker_args = {a: v for a, v in zip(arg_names[-len(defaults) :], defaults)}
            marker_args.update(marker.kwargs)
            marker_args.update({k: v for k, v in zip(arg_names, marker.args)})

            self.tests.setdefault(function, {}).setdefault(module, []).append(
                marker_function((self, function, module), **marker_args)
            )

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

        if not self.data:
            return

        # Prepare stats
        for sample in self.data:
            try:
                self.stats.update(Sample.parse(sample))
            except InvalidSample:
                pass

        for function, modules in self.tests.items():
            for module, markers in modules.items():
                test_stats = self._find_test(function, module)
                if test_stats is None:
                    # The test was not found. Either there is no such test or
                    # Austin did not collect any statistics for it.
                    continue

                total_test_time = sum(fs.total.time for fs in test_stats)
                total_test_malloc = sum(
                    fs.total.time if self.mode == "-m" else fs.total.memory_alloc
                    for fs in test_stats
                )
                total_test_dealloc = (
                    sum(fs.total.memory_dealloc for fs in test_stats)
                    if self.mode == "-f"
                    else 0
                )

                for marker in markers:
                    outcome = marker(
                        test_stats,
                        total_test_time,
                        total_test_malloc,
                        total_test_dealloc,
                    )
                    self.report.append((function, module, outcome))

        return sum(1 for outcome in self.report if not outcome[2])

    def start(self) -> None:
        """Start Austin."""
        args = ["-t", "10", "-i", self.interval, "-p", str(os.getpid())]
        if self.mode:
            args.append(self.mode)
        if self.children:
            args.append("-C")

        super().start(args)
