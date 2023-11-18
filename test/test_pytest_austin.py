from datetime import timedelta as td
from textwrap import dedent

from pytest_austin import _parse_time


def test_parse_time():
    assert _parse_time(td(microseconds=10), 0) == 10


def test_austin_time_checks(testdir):
    """Test Austin time checks."""

    # create a temporary pytest test file
    testdir.makepyfile(dedent(
        """
        import pytest

        def fibonacci(n):
            if n in (0, 1):
                return 1
            return fibonacci(n-1) + fibonacci(n-2)

        @pytest.mark.austin("50.3141592653 %", line=19)
        def test_lines():
            fibonacci(27)
            fibonacci(25)
    """)
    )

    result = testdir.runpytest("-vs", "--austin-report", "full")

    assert result.ret > 0
