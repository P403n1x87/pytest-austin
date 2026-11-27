import io
import os
from datetime import timedelta as td
from time import time
from typing import Any, Callable, Dict, Iterable, List, Optional, TextIO, Tuple, Union

from austin.events import AustinFrame, AustinMetadata, AustinSample
from austin.format.mojo import MojoStreamWriter
from austin.format.pprof import PProf
from austin.format.speedscope import Speedscope
from austin.simple import SimpleAustin
from austin.stats import AustinStats, AustinStatsType, FrameStats

import pytest_austin.markers as _markers

Microseconds = int
Bytes = int


def _find_from_hierarchy(
    collector: List[FrameStats],
    stats_list: Dict[AustinFrame, FrameStats],
    function: str,
    module: str,
) -> None:
    for label, stats in stats_list.items():
        if label.function == function and label.filename.endswith(module):
            collector.append(stats)
        else:
            _find_from_hierarchy(collector, stats.children, function, module)


def _parse_time(
    timedelta: Union[td, str, float, int], total_test_time: Microseconds
) -> Microseconds:
    if isinstance(timedelta, td):
        return int(timedelta.total_seconds() * 1e6)
    if isinstance(timedelta, str):
        perc = timedelta.strip()
        if not perc[-1] == "%":
            raise ValueError("Invalid % total time")
        return int(float(perc[:-1]) / 100 * total_test_time)
    if isinstance(timedelta, float) or isinstance(timedelta, int):
        return int(timedelta)

    raise ValueError(f"Invalid time delta type {type(timedelta)}")


class PyTestAustin(SimpleAustin):
    """pytest implementation of Austin."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        self.stats = AustinStats(stats_type=AustinStatsType.WALL)
        self.interval: str = "100"
        self.children = False
        self.mode: Optional[str] = None
        self.data: List[AustinSample] = []
        self.global_stats: Optional[str] = None
        self.austinfile: Optional[str] = None
        self.tests: Dict[str, Dict[str, List[Callable[..., _markers.CheckOutcome]]]] = (
            {}
        )
        self.report: List[Tuple[str, str, _markers.CheckOutcome]] = []
        self.report_level = "minimal"
        self.format = "austin"

    def on_sample(self, sample: AustinSample) -> None:
        """Sample received callback."""
        # We collect all the samples and only parse them at the end for
        # performance
        self.data.append(sample)

    def on_terminate(self) -> None:
        """Terminate callback."""
        self.global_stats = None

    def dump(self, stream: Optional[TextIO] = None) -> None:
        """Dump the collected statistics to the given IO stream.

        If no stream is given, the data is dumped into a file prefixed with
        ``.austin_`` and followed by a truncated timestamp within the pytest
        rootdir.
        """
        if not self.data:
            return

        def _dump(filename: str, stream: Optional[TextIO], dumper: Any) -> None:
            if stream is None:
                with open(
                    filename, "wb" if filename.endswith(("pprof", "aprof")) else "w"
                ) as fout:
                    dumper.dump(fout)
                    self.austinfile = os.path.join(os.getcwd(), filename)
            else:
                dumper.dump(stream)

        def _dump_austin() -> None:
            buffer = io.BytesIO()
            writer = MojoStreamWriter(buffer)
            writer.write(AustinMetadata(name="mode", value=self.stats.stats_type.value))
            for sample in self.data:
                writer.write(sample)

            class _AustinDumper:
                def __init__(self, buffer: Any) -> None:
                    self.buffer = buffer

                def dump(self, stream: Any) -> None:
                    stream.write(self.buffer.getvalue())

            _dump(
                f".austin_{int((time() * 1e6) % 1e14)}.aprof",
                stream,
                _AustinDumper(buffer),
            )

        def _dump_pprof() -> None:
            pprof = PProf(mode=self.stats.stats_type.value)
            for sample in self.data:
                pprof.add_sample(sample)
            _dump(
                f".austin_{int((time() * 1e6) % 1e14)}.pprof",
                stream,
                pprof,
            )

        def _dump_speedscope() -> None:
            name = f"austin_{int((time() * 1e6) % 1e14)}"
            speedscope = Speedscope(name, mode=self.stats.stats_type.value)
            for sample in self.data:
                speedscope.add_sample(sample)
            _dump(f".{name}.json", stream, speedscope)

        {"austin": _dump_austin, "pprof": _dump_pprof, "speedscope": _dump_speedscope}[
            self.format
        ]()

    def _index(self) -> Dict[str, Dict[str, List[FrameStats]]]:
        # TODO: This code can be optimised. If we collect all the test items we
        # can index up to the test functions. Then we keep indexing whenever
        # we are checking eaech marked test.

        index: Dict[str, Dict[str, List[FrameStats]]] = {}

        def _add_frame(stats: FrameStats) -> None:
            index.setdefault(stats.label.function, {}).setdefault(
                stats.label.filename, []
            ).append(stats)
            for child in stats.children.values():
                _add_frame(child)

        for _, process in self.stats.processes.items():
            for thread in process.threads.values():
                for frame_stats in thread.children.values():
                    _add_frame(frame_stats)

        return index

    def register_test(self, function: str, module: str, markers: Iterable[Any]) -> None:
        """Register a test with pytest-austin.

        We pass the test item name and module together with any markers.
        """
        for marker in markers:
            check_function = getattr(_markers, marker.name, None)
            if check_function is None:
                continue

            check = check_function(
                (self, function, module), *marker.args, **marker.kwargs
            )
            self.tests.setdefault(function, {}).setdefault(module, []).append(check)

    def _find_test(self, function: str, module: str) -> Optional[List[FrameStats]]:
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
            return 0

        # Prepare stats
        self.stats.stats_type = (
            AustinStatsType.MEMORY_ALLOC if self.mode == "-m" else AustinStatsType.WALL
        )
        for sample in self.data:
            self.stats.update(sample)

        for function, modules in self.tests.items():
            for module, checks in modules.items():
                test_stats = self._find_test(function, module)
                if test_stats is None:
                    # The test was not found. Either there is no such test or
                    # Austin did not collect any statistics for it.
                    continue

                total_test_time = sum(fs.total for fs in test_stats)
                total_test_malloc = (
                    sum(fs.total for fs in test_stats) if self.mode == "-m" else 0
                )
                total_test_dealloc = (
                    sum(fs.total for fs in test_stats) if self.mode == "-f" else 0
                )

                for check in checks:
                    outcome = check(
                        test_stats,
                        total_test_time,
                        total_test_malloc,
                        total_test_dealloc,
                    )
                    self.report.append((function, module, outcome))

        return sum(1 for outcome in self.report if not outcome[2])
