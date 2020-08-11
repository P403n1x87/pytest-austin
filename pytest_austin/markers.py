from dataclasses import dataclass
from datetime import timedelta as td
from typing import Any, Dict, List, NewType, Tuple, Type

from ansimarkup import parse
from austin.stats import Frame, FrameStats


Microseconds = NewType("Microseconds", int)
Bytes = NewType("Bytes", int)


@dataclass
class CheckOutcome:
    """Check outcome representation."""

    mark: Tuple[str, str, int]
    actual: float
    expected: float
    units: Type
    result: bool

    @staticmethod
    def _format_size(size):
        if size > (1 << 30):
            return f"{size / (1 << 30):.1f} GB"
        if size > (1 << 20):
            return f"{size / (1 << 20):.1f} MB"
        if size > (1 << 10):
            return f"{size / (1 << 10):.1f} KB"
        return f"{size} B"

    @staticmethod
    def _format_time(time):
        if time > 1e6:
            return f"{time / 1e6:.1f} s"
        if time > 1e3:
            return f"{time / 1e3:.1f} ms"
        return f"{time:.1f} μs"

    def __bool__(self):
        """Return the outcome result."""
        return self.result

    def __str__(self):
        """Give a human readable description of the outcome."""
        delta = self.actual - self.expected
        perc = delta * 100 / self.expected

        function, module, line = self.mark

        line_mark = f":<yellow>{line}</yellow>" if line else ""
        what = f"<bold>{function}</bold>{line_mark} (<cyan>{module}</cyan>)"

        formatter = {Microseconds: self._format_time, Bytes: self._format_size}[
            self.units
        ]

        how_much = (
            f"<red>+{formatter(delta)}</red>"
            if delta > 0
            else f"<green>-{formatter(-delta)}</green>"
        )
        return parse(
            f"{what} <bold>{how_much}</bold> <fg 128,128,128>({perc:.1f}% of {formatter(self.expected)})</fg 128,128,128>"
        )


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
    try:
        if isinstance(timedelta, td):
            return timedelta.total_seconds() * 1e6
        if isinstance(timedelta, str):
            perc = timedelta.strip()
            if not perc[-1] == "%":
                raise ValueError("Invalid % total time")
            return float(perc[:-1]) / 100 * total_test_time
        if isinstance(timedelta, float) or isinstance(timedelta, int):
            return timedelta
    except ValueError:
        pass

    raise ValueError(f"Invalid time delta type {type(timedelta)}")


def _parse_memory(size: Any, total_memory: Bytes) -> Bytes:
    try:
        if isinstance(size, str):
            _ = size.strip().upper()
            if _[-1] == "%":
                return float(_[:-1]) / 100 * total_memory
            if _.endswith("GB"):
                return int(_[:-2]) << 30
            if _.endswith("MB"):
                return int(_[:-2]) << 20
            if _.endswith("KB"):
                return int(_[:-2]) << 10
            if _.endswith("B"):
                return int(_[:-2])
        if isinstance(size, int):
            return size
    except ValueError:
        pass

    raise ValueError(f"Invalid memory size format or type {type(size)}")


def total_time(mark, time, function=None, module=None, line=0):
    """
    Check that the marked line doesn't take more than the given time delta to
    execute. If no line is given, then the whole function is considered.
    """
    _, test_function, test_module = mark
    function = function or test_function
    module = module or test_module

    def _(test_stats, total_test_time, total_test_malloc, total_test_dealloc):
        # find by function and module from index
        function_stats = []
        _find_from_hierarchy(
            function_stats, {s.label: s for s in test_stats}, function, module,
        )

        if line:
            function_stats = [fs for fs in function_stats if fs.label.line == line]

        function_total_time = sum(fs.total.time for fs in function_stats)

        expected_time = _parse_time(time, total_test_time)
        outcome = function_total_time <= expected_time

        return CheckOutcome(
            mark=(function, module, line),
            actual=function_total_time,
            expected=expected_time,
            units=Microseconds,
            result=outcome,
        )

    return _


def total_memory(mark, size, function=None, module=None, line=0, net=False):
    """
    Check that the marked line doesn't allocate more than the given memory to
    execute. If no line is given, then the whole function is considered. If net
    is set to ``True`` it will consider the net memory usage, that is the sum
    between memory allocations and deallocations.
    """
    pytest_austin, test_function, test_module = mark
    function = function or test_function
    module = module or test_module

    def _(test_stats, total_test_time, total_test_malloc, total_test_dealloc):
        # find by function and module from index
        function_stats = []
        _find_from_hierarchy(
            function_stats, {s.label: s for s in test_stats}, function, module,
        )

        if line:
            function_stats = [fs for fs in function_stats if fs.label.line == line]

        function_total_alloc = sum(
            fs.total.time if pytest_austin.mode == "-m" else fs.total.memory_alloc
            for fs in function_stats
        )
        function_total_dealloc = sum(fs.total.memory_dealloc for fs in function_stats)

        total_memory = (
            total_test_malloc if not net else total_test_malloc + total_test_dealloc
        )
        function_memory = (
            function_total_alloc
            if not net
            else function_total_alloc + function_total_dealloc
        )
        expected_memory = _parse_memory(size, total_memory)
        outcome = function_memory <= expected_memory

        return CheckOutcome(
            mark=(function, module, line),
            actual=function_memory,
            expected=expected_memory,
            units=Bytes,
            result=outcome,
        )

    return _
