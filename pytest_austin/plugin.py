from austin import AustinTerminated
from pytest import Function, hookimpl, Module
from pytest_austin import PyTestAustin


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
        "total_time(time, function, module, line): check that the marked line "
        "doesn't take more than the given time delta to execute. If no line is given, "
        "then the whole function is considered.",
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


def pytest_runtest_setup(item) -> None:
    """Register tests and checks with pytest-austin."""
    pytest_austin = item.config.pluginmanager.getplugin("austin")
    if not pytest_austin:
        return

    if pytest_austin.is_running():
        if isinstance(item, Function) and isinstance(item.parent, Module):
            function, module = item.name, item.parent.name
            pytest_austin.register_test(
                function, module, item.iter_markers("total_time")
            )


@hookimpl(hookwrapper=True)
def pytest_runtestloop(session):
    """Run all checks at the end and set the exit status."""
    yield

    # This runs effectively at the end of the session
    pytest_austin = session.config.pluginmanager.getplugin("austin")
    if not pytest_austin:
        return

    if pytest_austin.is_running():
        pytest_austin.terminate(wait=True)

    try:
        pytest_austin.join()
    except AustinTerminated:
        pass

    pytest_austin.dump()

    session.testsfailed += pytest_austin.check_tests()


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
    if pytest_austin.report:
        n = len(pytest_austin.report)

        for function, module, args, _, actual, expected, _ in pytest_austin.report:
            delta = actual - expected
            perc = delta * 100 / expected
            message = (
                f"{module}::{function} Function {args['function']} ({args['module']}) "
                f"took {int(delta)} μs ({perc:.1f}%) longer than expected ({int(expected)} μs)"
            )
            terminalreporter.write_line(message)

        terminalreporter.write_line("")
        terminalreporter.write_sep(
            "=", f"{n} check{'s' if n > 1 else ''} failed", red=True, bold=True,
        )
        terminalreporter.write_line("")
