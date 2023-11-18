from functools import partial

import pytest
from _pytest.runner import call_and_report
from _pytest.runner import \
    pytest_runtest_protocol as default_pytest_runtest_protocol

from pytest_austin import PyTestAustin
from pytest_austin.marker import austin_marker_handler


def pytest_addoption(parser, pluginmanager) -> None:
    """Add Austin command line options to pytest."""
    group = parser.getgroup("austin", "statistical profiling with Austin")

    group.addoption(
        "--steal-mojo",
        action="store_true",
        default=False,
        help="Disable Austin profiling",
    )

    group.addoption(
        "--profile-mode",
        choices=["time", "memory", "all"],
        default="time",
        help="The profile mode. Defaults to 'time'",
    )

    group.addoption(
        "--sampling-interval",
        type=int,
        default=100,
        help="Austin sampling interval in μs. Defaults to 100 μs",
    )

    group.addoption(
        "--minime",
        action="store_true",
        default=False,
        help="Profile any child processes too",
    )

    group.addoption(
        "--profile-format",
        choices=["austin", "speedscope", "pprof"],
        default="austin",
        help="Output profiler data file format. Defaults to 'austin'",
    )

    group.addoption(
        "--austin-report",
        choices=["minimal", "full"],
        default="minimal",
        help="The verbosity of the Austin checks report. By default, only failed"
        "checks are reported.",
    )


def pytest_configure(config) -> None:
    """Configure pytest-austin."""
    # Register all markers
    config.addinivalue_line(
        "markers",
        """austin(max_cpu, max_time, max_memory, function, file, line):
            TODO
        """,
    )

    if config.option.steal_mojo:
        # No mojo :(
        return

    # Required for when testing with pytester in-process
    pytest_austin = PyTestAustin()

    if config.option.profile_mode != "time":
        pytest_austin.mode = {"memory": "-m", "all": "-f"}[config.option.profile_mode]

    pytest_austin.interval = str(config.option.sampling_interval)
    pytest_austin.children = config.option.minime
    pytest_austin.report_level = config.option.austin_report
    pytest_austin.format = config.option.profile_format

    config.pluginmanager.register(pytest_austin, "austin")


@pytest.hookimpl(tryfirst=True)
def pytest_runtest_protocol(item):
    if item.get_closest_marker("skip"):
        return default_pytest_runtest_protocol(item, None)

    skipif = item.get_closest_marker("skipif")
    if skipif and skipif.args[0]:
        return default_pytest_runtest_protocol(item, None)

    marker = item.get_closest_marker("austin")
    if marker:
        ihook = item.ihook
        base_name = item.nodeid

        nodeid = base_name

        # Start
        ihook.pytest_runtest_logstart(nodeid=nodeid, location=item.location)

        # Setup
        report = call_and_report(item, "setup", log=False)
        report.nodeid = nodeid
        ihook.pytest_runtest_logreport(report=report)

        # Call
        item.runtest = partial(austin_marker_handler, item)
        report = call_and_report(item, "call", log=False)
        report.nodeid = nodeid
        ihook.pytest_runtest_logreport(report=report)

        # Teardown
        report = call_and_report(item, "teardown", log=False, nextitem=None)
        report.nodeid = nodeid
        ihook.pytest_runtest_logreport(report=report)

        # Finish
        ihook.pytest_runtest_logfinish(nodeid=nodeid, location=item.location)

        return True

def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Report Austin statistics if we had mojo."""
    pytest_austin = config.pluginmanager.getplugin("austin")
    if not pytest_austin:
        return

    terminalreporter.write_sep("=", "Austin report")
    terminalreporter.write_line(f"austin {pytest_austin.version}")
    if not pytest_austin.data:
        terminalreporter.write_line("No data collected.")
        return

    if pytest_austin.austinfile is not None:
        terminalreporter.write_line(
            f"Collected stats written on {pytest_austin.austinfile}\n"
        )

        if pytest_austin.global_stats:
            terminalreporter.write_line(pytest_austin.global_stats + "\n")
        else:
            terminalreporter.write_line(
                f"Austin collected a total of {len(pytest_austin.data)} samples\n"
            )

    # Report failed Austin conditions
    checks = pytest_austin.report
    failed_checks = [check for check in checks if not check[2]]
    if pytest_austin.report_level == "minimal":
        checks = failed_checks

    if checks:
        n = len(failed_checks)

        for function, module, outcome in checks:
            terminalreporter.write_line(f"{module}::{function} {outcome}")

        terminalreporter.write_line("")
        terminalreporter.write_sep(
            "=", f"{n} check{'s' if n > 1 else ''} failed", red=True, bold=True,
        )
        terminalreporter.write_line("")
