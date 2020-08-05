from datetime import timedelta as td
import os
import os.path

from pytest_austin import _parse_time


def test_parse_time():
    assert _parse_time(td(microseconds=10), 0) == 10


def test_austin_checks(testdir):
    """Make sure that our plugin works."""

    # create a temporary pytest test file
    testdir.makepyfile(
        """
        from datetime import timedelta as td
        from time import sleep

        import pytest

        def hello(name="World"):
            return "Hello {name}!".format(name=name)

        def fibonacci(n):
            if n in (0, 1):
                return 1
            return fibonacci(n-1) + fibonacci(n-2)

        @pytest.mark.total_time(td(milliseconds=50), function="fibonacci")
        @pytest.mark.total_time("99%", line=18)
        @pytest.mark.total_time("50.3141592653%", line=19)
        def test_lines():
            fibonacci(27)
            fibonacci(25)

        @pytest.mark.total_time(td(microseconds=1000))
        def test_check_fails():
            sleep(.1)
            assert hello() == "Hello World!"

        @pytest.mark.total_time(td(milliseconds=110))
        def test_check_succeeds():
            sleep(.1)
            assert hello() == "Hello World!"
    """
    )

    result = testdir.runpytest("-vs")

    assert result.ret > 0

    # We expect a single austin file
    (austin_file,) = [
        file for file in os.listdir(testdir.tmpdir) if file.startswith(".austin")
    ]
    assert austin_file

    # check that we have profiled test_hello_default
    with open(os.path.join(testdir.tmpdir, austin_file), "r") as fin:
        assert "test_lines" in fin.read()
