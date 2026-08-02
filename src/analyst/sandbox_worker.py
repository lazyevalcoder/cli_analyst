import ast
import io
import pickle
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.analyst.sandbox import (
    BLOCKED_SUBSTRINGS,
    DENIED_ATTRIBUTES,
    FORBIDDEN_AST_NODES,
    PANDAS_EXEC_METHODS,
    SAFE_BUILTINS,
    _check_ast_safe,
)

_SKIP = {"pd", "json", "np", "math"}


def _inject_modules(namespace: dict) -> None:
    import json

    import pandas as pd

    namespace["pd"] = pd
    namespace["json"] = json
    try:
        import numpy as np

        namespace["np"] = np
    except ImportError:
        pass
    try:
        import math

        namespace["math"] = math
    except ImportError:
        pass


def _write_out(namespace: dict, out_path: str) -> None:
    to_pickle = {k: v for k, v in namespace.items() if k not in _SKIP and k != "__builtins__"}
    with open(out_path, "wb") as f:
        pickle.dump(to_pickle, f)


def _fail(namespace: dict, out_path: str, message: str) -> None:
    try:
        _write_out(namespace, out_path)
    except Exception:
        pass
    print(message, file=sys.stderr)
    sys.exit(1)


def main() -> None:
    code_path, state_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

    with open(code_path, encoding="utf-8") as f:
        code = f.read()
    with open(state_path, "rb") as f:
        namespace = pickle.load(f)

    _inject_modules(namespace)

    for keyword in BLOCKED_SUBSTRINGS:
        if keyword in code:
            _fail(namespace, out_path, f"Blocked: code contains restricted keyword '{keyword}'")

    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        _fail(namespace, out_path, f"Syntax error: {e}")

    msg = _check_ast_safe(tree)
    if msg:
        _fail(namespace, out_path, f"Blocked: {msg}")

    stdout_capture = io.StringIO()
    try:
        with redirect_stdout(stdout_capture):
            namespace["__builtins__"] = SAFE_BUILTINS
            exec(code, namespace, namespace)
    except Exception:
        try:
            _write_out(namespace, out_path)
        except Exception:
            pass
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)

    try:
        _write_out(namespace, out_path)
    except Exception:
        pass
    print(stdout_capture.getvalue(), end="")
    sys.exit(0)


if __name__ == "__main__":
    main()
