from types import SimpleNamespace

from austin.events import AustinFrame, AustinMetrics, AustinSample
from austin.stats import FrameStats

from pytest_austin import PyTestAustin
from pytest_austin.markers import (
    Bytes,
    CheckOutcome,
    Microseconds,
    total_memory,
    total_time,
)


def _frame(function: str, filename: str, line: int, total: int) -> FrameStats:
    return FrameStats(
        label=AustinFrame(filename=filename, function=function, line=line),
        own=total,
        total=total,
    )


def test_check_outcome_bool() -> None:
    outcome = CheckOutcome(
        mark=("fibonacci", "mod.py", 19),
        actual=1.0,
        expected=2.0,
        units=Microseconds,
        result=True,
    )
    assert outcome
    outcome = CheckOutcome(
        mark=("fibonacci", "mod.py", 19),
        actual=1.0,
        expected=2.0,
        units=Bytes,
        result=False,
    )
    assert not outcome


def test_check_outcome_str() -> None:
    outcome = CheckOutcome(
        mark=("fibonacci", "mod.py", 19),
        actual=1.0,
        expected=2.0,
        units=Microseconds,
        result=False,
    )
    assert "fibonacci" in str(outcome)


def test_total_time_check_passes() -> None:
    check = total_time((None, "test_lines", "mod.py"), "50%", line=19)
    outcome = check([_frame("test_lines", "mod.py", 19, 5_000)], 10_000, 0, 0)
    assert outcome


def test_total_time_check_fails() -> None:
    check = total_time((None, "test_lines", "mod.py"), "50%", line=19)
    outcome = check([_frame("test_lines", "mod.py", 19, 15_000)], 10_000, 0, 0)
    assert not outcome


def test_total_memory_check_fails() -> None:
    instance = SimpleNamespace(mode="-m")
    check = total_memory((instance, "test_lines", "mod.py"), "24 MB")
    outcome = check(
        [_frame("test_lines", "mod.py", 0, 30 * 1024 * 1024)], 0, 30 * 1024 * 1024, 0
    )
    assert not outcome


def _sample(function: str, filename: str, line: int, time: int) -> AustinSample:
    return AustinSample(
        pid=1,
        iid=0,
        thread="MainThread",
        metrics=AustinMetrics(time=time),
        frames=(AustinFrame(filename=filename, function=function, line=line),),
    )


def test_check_tests_fails_when_no_stats_found() -> None:
    austin = PyTestAustin()
    austin.register_test(
        "missing_function",
        "mod.py",
        [
            SimpleNamespace(
                name="total_time",
                args=("50%",),
                kwargs={"function": "missing_function"},
            )
        ],
    )
    austin.data = [_sample("other_function", "mod.py", 1, 1_000)]

    assert austin.check_tests() > 0
    assert len(austin.report) > 0
    assert not austin.report[0][2]
