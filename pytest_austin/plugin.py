import os
import os.path
from time import time

from austin import AustinTerminated
from pytest import hookimpl
from pytest import Function, Module
from pytest_austin import PyTestAustin

AUSTIN_DUMP = None


def pytest_addoption(parser, pluginmanager) -> None:
    """Add Austin command line options to pytest."""
    group = parser.getgroup("austin", "statistical profiling with Austin")

    parser.addini("austin", "Austin options", "args")

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
        help="The profile mode. Defaults to 'time'.",
    )

    group.addoption(
        "--sampling-interval",
        type=int,
        default=100,
        help="Austin sampling interval in μs. Defaults to 100 μs.",
    )

    group.addoption(
        "--minime",
        action="store_true",
        default=False,
        help="Profile any child processes too.",
    )


def pytest_configure(config) -> None:
    """Configure pytest-austin."""
    config.addinivalue_line(
        "markers",
        "total_time(timedelta): check that the marked test doesn't take more than the "
        "given time delta to execute.",
    )

    if config.option.steal_mojo:
        return

    # Required for when testing with pytester in-process
    pytest_austin = PyTestAustin()

    if config.option.profile_mode != "time":
        pytest_austin.mode = {"memory": "-m", "all": "-f"}[config.option.profile_mode]

    pytest_austin.interval = str(config.option.sampling_interval)
    pytest_austin.children = config.option.minime

    config.pluginmanager.register(pytest_austin, "austin")


def pytest_sessionstart(session) -> None:
    """Start Austin if we have mojo."""
    pytest_austin = session.config.pluginmanager.getplugin("austin")
    if not pytest_austin:
        return

    pytest_austin.start()
    pytest_austin.wait_ready(1)


@hookimpl(hookwrapper=True)
def pytest_runtestloop(session):
    yield

    session.testsfailed += 1


def pytest_runtest_setup(item) -> None:
    # TODO
    if isinstance(item, Function) and isinstance(item.parent, Module):
        function, module = item.name, item.parent.name
        total_time_markers = list(item.iter_markers("total_time"))
        if total_time_markers:
            (marker,) = total_time_markers
            print(f"{function} ({module}) :: {marker.args[0]}")


def pytest_sessionfinish(session, exitstatus) -> None:
    """Stop Austin if we had mojo."""
    global AUSTIN_DUMP

    pytest_austin = session.config.pluginmanager.getplugin("austin")
    if not pytest_austin:
        return

    if pytest_austin.is_running():
        pytest_austin.terminate(wait=True)
        try:
            pytest_austin.join()
        except AustinTerminated:
            pass

        filename = f".austin_{int((time() * 1e6) % 1e14)}"
        with open(filename, "w") as fout:
            pytest_austin.dump(fout)
            AUSTIN_DUMP = os.path.join(os.getcwd(), filename)


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Report Austin statistics if we had mojo."""
    pytest_austin = config.pluginmanager.getplugin("austin")
    if not pytest_austin:
        return

    terminalreporter.write_sep("=", "Austin report")

    if not pytest_austin.data:
        terminalreporter.write_line("No data collected.")
        return

    if AUSTIN_DUMP is not None:
        terminalreporter.write_line(f"Collected stats written on {AUSTIN_DUMP}")

        for line in pytest_austin.global_stats.splitlines():
            terminalreporter.write_line(line)
        if not pytest_austin.global_stats:
            terminalreporter.write_line(
                f"Austin collected a total of {len(pytest_austin.data)} samples"
            )

    # Report failed Austin conditions
    failed = True
    markup = {"red": True, "bold": True} if failed else {"green": True}
    message = "Some Austin conditions failed."
    terminalreporter.write_line(message, **markup)
