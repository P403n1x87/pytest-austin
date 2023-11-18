import ast
import os
import subprocess
import sys
import time
from importlib._bootstrap_external import _code_to_timestamp_pyc as code_to_pyc
from pathlib import Path
from tempfile import NamedTemporaryFile


def dump_code_to_file(code, file):
    file.write(code_to_pyc(code, time.time(), len(code.co_code)))
    file.flush()


class FunctionDefFinder(ast.NodeVisitor):
    def __init__(self, func_name):
        super(FunctionDefFinder, self).__init__()
        self.func_name = func_name
        self._body = None

    def generic_visit(self, node):
        return self._body or super(FunctionDefFinder, self).generic_visit(node)

    def visit_FunctionDef(self, node):
        if node.name == self.func_name:
            self._body = node.body

    def find(self, file):
        with open(file) as f:
            t = ast.parse(f.read())
            self.visit(t)
            t.body = self._body
            return t

def invoke_austin(*args, **kwargs):
    timeout = kwargs.pop("timeout", None)
    close_fds = sys.platform != "win32"
    subp = subprocess.Popen(("austin", "-Pb", *args), stdout=subprocess.PIPE, stderr=subprocess.PIPE, close_fds=close_fds, **kwargs)

    subp.wait() # TODO: Check no errors

    try:
        stdout, stderr = subp.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        subp.terminate()
        stdout, stderr = subp.communicate(timeout=timeout)

    # TODO: Convert stdout to Austin stats with MojoFile and return the stats

def austin_marker_handler(item):
    file, _, func = item.location

    # Override environment variables for the subprocess
    env = os.environ.copy()
    pythonpath = os.getenv("PYTHONPATH", None)
    cwd = str(Path.cwd().resolve())
    env["PYTHONPATH"] = os.pathsep.join((cwd, pythonpath)) if pythonpath is not None else cwd

    with NamedTemporaryFile(mode="wb", suffix=".pyc") as fp:
        dump_code_to_file(compile(FunctionDefFinder(func).find(file), file, "exec"), fp.file)
        def _subprocess_wrapper():
            stats = invoke_austin(sys.executable, fp.name, env=env)

            # TODO: Query stats according to marker options

        return _subprocess_wrapper()


