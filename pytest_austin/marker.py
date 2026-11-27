import ast
import sys
from importlib._bootstrap_external import _code_to_timestamp_pyc as code_to_pyc  # type: ignore[attr-defined]
from tempfile import NamedTemporaryFile
from time import time
from typing import Any, List, Optional


def dump_code_to_file(code: Any, file: Any) -> None:
    """Dump the given compiled code object into the given file."""
    file.write(code_to_pyc(code, time(), len(code.co_code)))
    file.flush()


class FunctionDefFinder(ast.NodeVisitor):
    """Find the body of a function by its name."""

    def __init__(self, func_name: str) -> None:
        """Initialize the finder with the function name to look for."""
        super().__init__()
        self.func_name = func_name
        self._body: List[ast.stmt] = []
        self._node: Optional[ast.FunctionDef] = None

    def generic_visit(self, node: ast.AST) -> Any:
        """Visit the children of the given node, unless the body is cached."""
        return self._body or super().generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        """Visit function definition nodes, caching the one we look for."""
        if node.name == self.func_name:
            self._body = node.body
            self._node = node
        self.generic_visit(node)

    def find(self, file: str) -> ast.Module:
        """Find the function definition node in the given file."""
        with open(file) as f:
            t = ast.parse(f.read())
            self.visit(t)
            if self._node is None:
                t.body = self._body
            else:
                profile_functions = []
                for node in t.body:
                    if isinstance(node, ast.FunctionDef):
                        node.decorator_list = []
                        profile_functions.append(node)
                t.body = [
                    *profile_functions,
                    ast.Expr(
                        value=ast.Call(
                            func=ast.Name(id=self.func_name, ctx=ast.Load()),
                            args=[],
                            keywords=[],
                        ),
                    ),
                ]
            ast.fix_missing_locations(t)
            return t


def austin_marker_handler(item: Any) -> None:
    """Run a single test function under Austin and collect its stats."""
    file, _, func = item.location

    pytest_austin = item.config.pluginmanager.get_plugin("austin")

    markers = [
        marker
        for marker in item.iter_markers()
        if marker.name in ("total_time", "total_memory")
    ]
    pytest_austin.register_test(func, file, markers)

    pytest_austin.data = []
    pytest_austin.report = []

    with NamedTemporaryFile(mode="wb", suffix=".pyc") as fp:
        dump_code_to_file(
            compile(FunctionDefFinder(func).find(file), file, "exec"), fp.file
        )
        fp.flush()
        args = ["-i", str(pytest_austin.interval)]
        if pytest_austin.mode:
            args.append(pytest_austin.mode)
        args.append(sys.executable)
        args.append(fp.name)
        pytest_austin.start(args)
        pytest_austin.wait()

    if pytest_austin.check_tests() > 0:
        raise RuntimeError("One or more Austin checks have failed.")
