import ast
import builtins
import concurrent.futures
import io
import json
import traceback
from contextlib import redirect_stdout

import pandas as pd

from config import CONFIG

BLOCKED_SUBSTRINGS = [
    "import os", "import sys", "import subprocess", "import shutil",
    "import pathlib", "open(", "exec(", "eval(", "compile(",
    "__import__", "globals(", "locals(", "vars(",
    "breakpoint", "pdb", "importlib",
]

SAFE_BUILTINS = {
    "print": builtins.print,
    "len": builtins.len,
    "range": builtins.range,
    "int": builtins.int,
    "float": builtins.float,
    "str": builtins.str,
    "bool": builtins.bool,
    "list": builtins.list,
    "dict": builtins.dict,
    "tuple": builtins.tuple,
    "set": builtins.set,
    "sorted": builtins.sorted,
    "reversed": builtins.reversed,
    "enumerate": builtins.enumerate,
    "zip": builtins.zip,
    "map": builtins.map,
    "filter": builtins.filter,
    "sum": builtins.sum,
    "min": builtins.min,
    "max": builtins.max,
    "abs": builtins.abs,
    "round": builtins.round,
    "repr": builtins.repr,
    "format": builtins.format,
    "ValueError": builtins.ValueError,
    "TypeError": builtins.TypeError,
    "KeyError": builtins.KeyError,
    "IndexError": builtins.IndexError,
    "Exception": builtins.Exception,
}

DENIED_ATTRIBUTES = {
    "__import__", "__builtins__", "__class__", "__bases__",
    "__subclasses__", "__globals__", "__code__", "__closure__",
    "__dict__", "__init__", "__getattribute__", "__reduce__",
}

PANDAS_EXEC_METHODS = {"eval", "query", "exec"}

FORBIDDEN_AST_NODES = (ast.Import, ast.ImportFrom)


def _check_ast_safe(tree: ast.AST) -> str | None:
    for node in ast.walk(tree):
        if isinstance(node, FORBIDDEN_AST_NODES):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [a.name for a in node.names]
            return f"import statements are not allowed: {', '.join(names)}"

        if isinstance(node, ast.Attribute):
            if node.attr in DENIED_ATTRIBUTES:
                return f"access to '{node.attr}' is not allowed"

        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Attribute):
                if fn.attr in DENIED_ATTRIBUTES:
                    return f"access to '{fn.attr}' is not allowed"
                if fn.attr in PANDAS_EXEC_METHODS:
                    return f"pandas method '{fn.attr}' is not allowed"
                if fn.attr == "__import__":
                    return "dynamic import is not allowed"
            if isinstance(fn, ast.Name) and fn.id in ("exec", "eval", "compile", "open", "__import__"):
                return f"'{fn.id}()' is not allowed"

        if isinstance(node, ast.Name):
            if node.id in ("exec", "eval", "compile", "open", "__import__"):
                return f"reference to '{node.id}' is not allowed"

    return None


def execute_code(code: str, df: pd.DataFrame) -> tuple[bool, str]:
    namespace = _make_namespace(df)
    return _execute_internal(code, namespace, df)


def execute_in_namespace(code: str, namespace: dict) -> tuple[bool, str]:
    return _execute_internal(code, namespace)


def _make_namespace(df: pd.DataFrame) -> dict:
    ns = {"df": df, "pd": pd, "json": json}
    try:
        import numpy as np
        ns["np"] = np
    except ImportError:
        pass
    return ns


def _execute_internal(code: str, namespace: dict, df: pd.DataFrame = None) -> tuple[bool, str]:
    for keyword in BLOCKED_SUBSTRINGS:
        if keyword in code:
            return False, f"Blocked: code contains restricted keyword '{keyword}'"

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, f"Syntax error: {e}"

    msg = _check_ast_safe(tree)
    if msg:
        return False, f"Blocked: {msg}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_code, code, SAFE_BUILTINS, namespace)
        try:
            output, error = future.result(timeout=CONFIG.timeout_seconds)
        except concurrent.futures.TimeoutError:
            return False, f"Code execution timed out after {CONFIG.timeout_seconds} seconds"

    if error:
        return False, error
    if not output.strip():
        return True, "(no output)"
    return True, output


def _run_code(code: str, safe_builtins: dict, namespace: dict) -> tuple[str, str]:
    stdout_capture = io.StringIO()
    try:
        with redirect_stdout(stdout_capture):
            exec(code, {"__builtins__": safe_builtins}, namespace)
        return stdout_capture.getvalue(), ""
    except Exception:
        return "", traceback.format_exc()
