import os
from threading import Event
from time import time
from typing import Optional

from austin import AustinTerminated
from austin.stats import AustinStats, Sample
from austin.threads import ThreadedAustin

# from pytest.config import Config, PytestPluginManager
# from pytest.config.argparsing import Parser
# from pytest.main import Session


class PyTestAustin(ThreadedAustin):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mojo = True
        self.ready = Event()
        self.stats = AustinStats()

    def on_ready(self, process, child_process, command_line):
        self.ready.set()

    def on_sample_received(self, sample):
        self.stats.update(Sample.parse(sample))

    def on_terminate(self, stats):
        self.ready.set()

    def wait_ready(self, timeout=None):
        self.ready.wait(timeout)

    def lose_mojo(self):
        self.mojo = False

    def retrieve_mojo(self):
        self.mojo = True

    def has_mojo(self):
        return self.mojo


PYTEST_AUSTIN = PyTestAustin()


# def pytest_addoption(parser: Parser, pluginmanager: PytestPluginManager) -> None:
def pytest_addoption(parser, pluginmanager) -> None:
    group = parser.getgroup("austin", "Statistical profiling of tests with Austin")
    group.addoption(
        "--steal-mojo",
        action="store_true",
        default=False,
        help="Disable Austin profiling",
    )


# def pytest_configure(config: Config):
def pytest_configure(config) -> None:
    if config.option.steal_mojo:
        PYTEST_AUSTIN.lose_mojo()
    else:
        # Required for when testing with pytester in-process
        PYTEST_AUSTIN.retrieve_mojo()


# def pytest_sessionstart(session: Session) -> None:
def pytest_sessionstart(session) -> None:
    if PYTEST_AUSTIN.has_mojo():
        print(f"!!!!!!!!!!!! PID {os.getpid()}")
        PYTEST_AUSTIN.start(["-i", "100", "-t", "1", "-Cp", str(os.getpid())])
        PYTEST_AUSTIN.wait_ready(1)


def pytest_sessionfinish(session, exitstatus) -> None:
    if PYTEST_AUSTIN.has_mojo() and PYTEST_AUSTIN.is_running():
        PYTEST_AUSTIN.terminate(wait=True)
        filename = "." + f"austin_{time()}".replace(".", "")
        with open(filename, "w") as fout:
            PYTEST_AUSTIN.stats.dump(fout)
