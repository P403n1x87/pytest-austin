from datetime import timedelta as td
import os
import os.path

from pytest_austin import _parse_time


def check_austin_dump(dir, needle):
    """Check that we have produced a profiler dump."""
    # We expect a single austin file
    (austin_file,) = [file for file in os.listdir(dir) if file.startswith(".austin")]
    assert austin_file

    with open(
        os.path.join(dir, austin_file), "rb" if austin_file.endswith(".pprof") else "r"
    ) as fin:
        assert needle in fin.read()


def test_parse_time():
    assert _parse_time(td(microseconds=10), 0) == 10


def test_austin_time_checks(testdir):
    """Test Austin time checks."""

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
        @pytest.mark.total_time("99 %", line=18)
        @pytest.mark.total_time("50.3141592653 %", line=19)
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

    result = testdir.runpytest("-vs", "--austin-report", "full")

    assert result.ret > 0

    check_austin_dump(testdir.tmpdir, "test_lines")


def test_austin_memory_checks(testdir):
    """Test Austin memory checks."""

    # create a temporary pytest test file
    testdir.makepyfile(
        """
        import pytest

        @pytest.mark.total_memory("50.3141592653 %")
        def test_memory_alloc_fails():
            a = [42]
            for i in range(20):
                a = list(a) + list(a)

        @pytest.mark.total_memory("128 MB")
        def test_memory_alloc_succeeds():
            a = [42]
            for i in range(20):
                a = list(a) + list(a)

        @pytest.mark.total_memory("12 MB", net=True)
        def test_memory_net_alloc():
            a = [42]
            for i in range(20):
                a = list(a) + list(a)

    """
    )

    result = testdir.runpytest(
        "-vs", "--profile-mode", "memory", "--profile-format", "pprof"
    )

    assert result.ret > 0

    check_austin_dump(testdir.tmpdir, b"test_memory_alloc")


def test_austin_full_checks(testdir):
    """Test Austin full checks."""

    # create a temporary pytest test file
    testdir.makepyfile(
        """
        import pytest

        @pytest.mark.total_time(1)
        @pytest.mark.total_memory("1 KB")
        def test_full_checks_fails():
            a = [42]
            for i in range(20):
                a = list(a) + list(a)
    """
    )

    result = testdir.runpytest(
        "-vs", "--profile-mode", "all", "--profile-format", "speedscope"
    )

    assert result.ret > 0

    check_austin_dump(testdir.tmpdir, "test_full_checks")
