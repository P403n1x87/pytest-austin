<p align="center">
  <br><img src="art/logo.png" alt="pytest-austin" /><br>
</p>

<h3 align="center">Python Performance Testing with Austin</h3>

<p align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/3/3a/Tux_Mono.svg"
       height="24px" />
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="https://upload.wikimedia.org/wikipedia/commons/f/fa/Apple_logo_black.svg"
       height="24px" />
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="https://upload.wikimedia.org/wikipedia/commons/2/2b/Windows_logo_2012-Black.svg"
       height="24px" />
</p>

<p align="center">
  <a href="https://github.com/P403n1x87/pytest-austin/actions?workflow=Tests">
    <img src="https://github.com/P403n1x87/pytest-austin/workflows/Tests/badge.svg"
         alt="GitHub Actions: Tests">
  </a>
  <a href="https://travis-ci.com/P403n1x87/pytest-austin">
    <img src="https://travis-ci.com/P403n1x87/pytest-austin.svg?token=fzW2yzQyjwys4tWf9anS"
         alt="Travis CI">
  </a>
  <a href="https://codecov.io/gh/P403n1x87/pytest-austin">
    <img src="https://codecov.io/gh/P403n1x87/pytest-austin/branch/master/graph/badge.svg"
         alt="Codecov">
  </a>
  <a href="https://pypi.org/project/pytest-austin/">
    <img src="https://img.shields.io/pypi/v/pytest-austin.svg"
         alt="PyPI">
  </a>
  <a href="https://github.com/P403n1x87/pytest-austin/blob/master/LICENSE.md">
    <img src="https://img.shields.io/badge/license-GPLv3-ff69b4.svg"
         alt="LICENSE">
  </a>
</p>

<p align="center">
  <a href="#synopsis"><b>Synopsis</b></a>&nbsp;&bull;
  <a href="#installation"><b>Installation</b></a>&nbsp;&bull;
  <a href="#usage"><b>Usage</b></a>&nbsp;&bull;
  <a href="#compatibility"><b>Compatibility</b></a>&nbsp;&bull;
  <a href="#contribute"><b>Contribute</b></a>
</p>

<p align="center">
  <a
    href="https://www.buymeacoffee.com/Q9C1Hnm28"
    target="_blank">
  <img
    src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png"
    alt="Buy Me A Coffee" />
  </a>
</p>

# Synopsis

The pytest-austin plugin for [pytest](https://docs.pytest.org/en/stable/) brings
Python performance testing right into your CI pipelines. It uses
[Austin](https://github.com/P403n1x87/austin) to profile your test runs without
any instrumentation. All you have to do is simply mark the tests on which you
want to execute checks for preventing performance regressions.

~~~ Python
import pytest


@pytest.mark.total_time(td(milliseconds=50), function="fibonacci")
@pytest.mark.total_time("99%", line=8)
@pytest.mark.total_time("50.3141592653%", line=9)
def test_hello_default():
    fibonacci(27)
    fibonacci(25)
~~~

Any failed tests will be reported by pytest at the end of the session. All the
collected statistics are written on a file prefixed with `austin_` and followed
by a truncated timestamp, inside pytest rootdir. You can drop it onto
[Speedscope](https://speedscope.app) for a quick visual representation of your
tests.

~~~
================================================================ test session starts ================================================================
platform linux -- Python 3.6.9, pytest-6.0.1, py-1.9.0, pluggy-0.13.1 -- /home/gabriele/.cache/pypoetry/virtualenvs/pytest-austin-yu27Ep_e-py3.6/bin/python3.6
cachedir: .pytest_cache
rootdir: /tmp/pytest-of-gabriele/pytest-226/test_austin_time_checks0
plugins: cov-2.10.0, austin-0.1.0
collecting ... collected 3 items

test_austin_time_checks.py::test_lines PASSED
test_austin_time_checks.py::test_check_fails PASSED
test_austin_time_checks.py::test_check_succeeds PASSED

=================================================================== Austin report ===================================================================
austin 2.0.0
Collected stats written on /tmp/pytest-of-gabriele/pytest-226/test_austin_time_checks0/.austin_97148135487643.aprof

🕑 Sampling time (min/avg/max) : 376/3327/18019 μs
🐢 Long sampling rate : 87/87 (100.00 %) samples took longer than the sampling interval
💀 Error rate : 0/87 (0.00 %) invalid samples

test_austin_time_checks.py::test_lines test_lines:19 (test_austin_time_checks.py) -16.0 ms (-78.2% of 20.5 ms)
test_austin_time_checks.py::test_lines test_lines:18 (test_austin_time_checks.py) -4.1 ms (-10.1% of 40.3 ms)
test_austin_time_checks.py::test_lines fibonacci (test_austin_time_checks.py) -9.3 ms (-18.6% of 50.0 ms)
test_austin_time_checks.py::test_check_fails test_check_fails (test_austin_time_checks.py) +99.8 ms (9978.6% of 1000.0 μs)
test_austin_time_checks.py::test_check_succeeds test_check_succeeds (test_austin_time_checks.py) -9.0 ms (-8.1% of 110.0 ms)

================================================================== 1 check failed ===================================================================

================================================================= 3 passed in 0.35s =================================================================
~~~


# Installation

pytest-austin can be installed directly from PyPI with

~~~ bash
pip install pytest-austin --upgrade
~~~

**NOTE** In order for the plugin to work, the Austin binary needs to be on the
``PATH`` environment variable. See [Austin
installation](https://github.com/P403n1x87/austin#installation) instructions to
see how you can easily install Austin on your platform.

For platform-specific issues and remarks, refer to the
[Compatibility](#compatibility) section below.


# Usage

Once installed, the plugin will try to attach Austin to the pytest process in
order to sample it every time you run pytest. If you want to prevent Austin from
profiling your tests, you have to steal its mojo. You can do so with the
`--steal-mojo` command line argument.


## Time checks

The plugin looks for the `total_time` marker on collected test items, which
takes a mandatory argument `time` and three optional ones: `function`, `module`
and `line`.

If you simply want to check that the duration of a test item doesn't take longer
than `time`, you can mark it with `@pytest.mark.total_time(time)`. Here, `time`
can either be a `float` (in seconds) or an instance of `datetime.timedelta`.

~~~ python
from datetime import timedelta as td

import pytest


@pytest.mark.total_time(td(milliseconds=50))
def test_hello_default():
    ...
~~~

In some cases, you would want to make sure that a function or method called on a
certain line in your test script executes in under a certain amount of time, say
5% of the total test time. You can achieve this like so

~~~ python
import pytest


@pytest.mark.total_time("5%", line=9)
def test_hello_default():
    somefunction()
    fastfunction()  # <- this is line no. 7 in the test script
    someotherfunction()
~~~

In many cases, however, one would want to test that a function or a method
called either directly or indirectly by a test doesn't take more than a certain
overall time to run. This is where the remaining arguments of the ``total_test``
marker come into play. Suppose that you want to profile the procedure ``bar``
that is called by method ``foo`` of an object  of type ``Snafu``. To ensure that
``bar`` doesn't take longer than, say, 50% of the overall test duration, you can
write

~~~ python
import pytest


@pytest.mark.total_time("50%", function="bar")
def test_snafu():
    ...
    snafu = Snafu()
    ...
    snafu.foo()
    ...
~~~

You can use the `module` argument to resolve function name clashes. For example,
if the definition of the function/method `bar` occurs within the modules
``somemodule.py`` and ``someothermodule.py``, but you are only interested in the
one defined in ``somemodule.py``, you can change the above into

~~~ python
import pytest


@pytest.mark.total_time("50%", function="bar", module="somemodule.py")
def test_snafu():
    ...
    snafu = Snafu()
    ...
    snafu.foo()
    ...
~~~

And whilst you can also specify a line number, this is perhaps not very handy
and practical outside of test scripts themselves, unless the content of the
module is stable enough that line numbers don't need to be updated very
frequently.

## Memory checks

One can perform memory allocation checks with the `total_memory` marker. The
first argument is ``size``, which can be a percentage of the total memory
allocation of the marked test case, as well as an absolute measure of the
maximum amount of memory, e.g., ``"24 MB"``. The ``function``, ``module`` and
``line`` are the same as for the ``total_time`` marker. The extra ``net``
argument can be set to ``True`` to check for the total _net_ memory usage, that
is the difference between memory allocations and deallocations.

~~~ python
import pytest


@pytest.mark.total_memory("24 MB")
def test_snafu():
    allota_memory()
~~~

In order to perform memory checks, you need to specify either the ``memory`` or
``all`` profile mode via the ``--profile-mode`` option.

## Mixed checks

When in the ``all`` profile mode, you can perform both time and memory checks by
stacking ``total_time`` and ``total_memory`` markers.

~~~ python
import pytest


@pytest.mark.total_time(5.15)
@pytest.mark.total_memory("24 MB")
def test_snafu():
    allota_memory_and_time()
~~~


## Multi-processing

If your tests spawn other Python processes, you can ask pytest-austin to profile
them too with the ``--minime`` option. Note that if your tests are spawning too
many non-Python processes, the sampling rate might be affected because of the
way that Austin tries to discover Python child processes.

## Reporting

This plugins generate a report on terminal and dumps the collected profiling
statistics on the file system as well, for later analysis and visualisation. The
verbosity of the terminal report can be controlled with the ``--austin-report``
option. By default, it is set to ``minimal``, which means that only checks that
have failed will be reported. Use ``full`` to see the results for all the checks
that have been detected and executed by the plugin.

Regarding the dump of the profiling statistics, the generated file is in the
Austin format by default (this is a generalisation of the collapsed stack
format). If you want the plugin to dump the data in either the ``pprof`` or
``speedscope`` format, you can set the ``--profile-format`` option accordingly.


# Compatibility

This plugin has been tested on Linux, MacOS and Windows. Given that it relies on
[Austin](https://github.com/P403n1x87/austin) for sampling the frame stacks of
the pytest process, its compatibility considerations apply to pytest-austin as
well.

On Linux, the use of ``sudo`` is required, unless the ``CAP_SYS_PTRACE``
capability is granted to the Austin binary with, e.g.

~~~ bash
sudo setcap cap_sys_ptrace+ep `which austin`
~~~

Then the use of ``sudo`` is no longer required to allow Austin to attach and
sample pytest.

On MacOS, the use of ``sudo`` is also mandatory, unless the user that is
invoking pytest belongs to the ``procmod`` group.


# Contribute

If you like pytest-austin and you find it useful, there are ways for you to
contribute.

If you want to help with the development, then have a look at the open issues
and have a look at the [contributing guidelines](CONTRIBUTING.md) before you
open a pull request.

You can also contribute to the development of the pytest-austin by becoming a
sponsor and/or by [buying me a coffee](https://www.buymeacoffee.com/Q9C1Hnm28)
on BMC or by chipping in a few pennies on
[PayPal.Me](https://www.paypal.me/gtornetta/1).

<p align="center">
  <a href="https://www.buymeacoffee.com/Q9C1Hnm28"
     target="_blank">
  <img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png"
       alt="Buy Me A Coffee" />
  </a>
</p>
