import ast
import os
import subprocess
import sys
import time
from importlib._bootstrap_external import _code_to_timestamp_pyc as code_to_pyc  # type: ignore[attr-defined]
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, List


def dump_code_to_file(code: Any, file: Any) -> None:
    """Dump the given compiled code object into the given file."""
    file.write(code_to_pyc(code, time.time(), len(code.co_code)))
    file.flush()


class FunctionDefFinder(ast.NodeVisitor):
    """Find the body of a function by its name."""

    def __init__(self, func_name: str) -> None:
        """Initialize the finder with the function name to look for."""
        super().__init__()
        self.func_name = func_name
        self._body: List[ast.stmt] = []

    def generic_visit(self, node: ast.AST) -> Any:
        """Visit the children of the given node, unless the body is cached."""
        return self._body or super().generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        """Visit function definition nodes, caching the one we look for."""
        if node.name == self.func_name:
            self._body = node.body
        self.generic_visit(node)

    def find(self, file: str) -> ast.Module:
        """Find the function definition node in the given file."""
        with open(file) as f:
            t = ast.parse(f.read())
            self.visit(t)
            t.body = self._body
            return t


def invoke_austin(*args: str, **kwargs: Any) -> None:
    """Invoke the Austin binary against the given Python process."""
    timeout = kwargs.pop("timeout", None)
    close_fds = sys.platform != "win32"
    subp = subprocess.Popen(
        ("austin", "-Pb", *args),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        close_fds=close_fds,
        **kwargs,
    )

    subp.wait()  # TODO: Check no errors

    try:
        stdout, stderr = subp.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subp.terminate()
        stdout, stderr = subp.communicate(timeout=timeout)

    # TODO: Convert stdout to Austin stats with MojoFile and return the stats


def austin_marker_handler(item: Any) -> None:
    """Run a single test function under Austin and collect its stats."""
    file, _, func = item.location

    # Override environment variables for the subprocess
    env = os.environ.copy()
    pythonpath = os.getenv("PYTHONPATH", None)
    cwd = str(Path.cwd().resolve())
    env["PYTHONPATH"] = (
        os.pathsep.join((cwd, pythonpath)) if pythonpath is not None else cwd
    )

    with NamedTemporaryFile(mode="wb", suffix=".pyc") as fp:
        dump_code_to_file(
            compile(FunctionDefFinder(func).find(file), file, "exec"), fp.file
        )

        def _subprocess_wrapper() -> None:
            invoke_austin(sys.executable, fp.name, env=env)

            # TODO: Query stats according to marker options

        return _subprocess_wrapper()
