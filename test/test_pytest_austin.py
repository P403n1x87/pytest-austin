import os
import os.path


def test_hello(testdir):
    """Make sure that our plugin works."""

    # create a temporary pytest test file
    testdir.makepyfile(
        """
        from datetime import timedelta as td
        from time import sleep

        import pytest

        def hello(name="World"):
            return "Hello {name}!".format(name=name)

        def test_hello_default():
            sleep(1)
            assert hello() == "Hello World!"

        @pytest.mark.total_time(td(microseconds=100))
        def test_hello_default():
            sleep(1)
            assert hello() == "Hello World!"
    """
    )

    testdir.runpytest("-vs")

    # We expect a single austin file
    (austin_file,) = [
        file for file in os.listdir(testdir.tmpdir) if file.startswith(".austin")
    ]
    assert austin_file

    # check that we have profiled test_hello_default
    with open(os.path.join(testdir.tmpdir, austin_file), "r") as fin:
        assert "test_hello_default" in fin.read()
