def test_hello(testdir):
    """Make sure that our plugin works."""

    # create a temporary conftest.py file
    testdir.makeconftest(
        """
        import pytest

        @pytest.fixture(params=[
            "Brianna",
            "Andreas",
            "Floris",
        ])
        def name(request):
            return request.param
    """
    )

    # create a temporary pytest test file
    testdir.makepyfile(
        """
        from time import sleep
        def hello(name="World"):
            return "Hello {name}!".format(name=name)

        def test_hello_default():
            # sleep(1)
            assert hello() == "Hello World!"

        def test_hello_name(name):
            assert hello(name) == "Hello {0}!".format(name)
    """
    )

    # run all tests with pytest
    result = testdir.runpytest("-vs")

    # check that all 4 tests passed
    # result.assert_outcomes(passed=4)
