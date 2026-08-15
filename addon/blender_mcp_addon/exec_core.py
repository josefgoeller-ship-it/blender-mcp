"""Runs Python against ``bpy`` and converts whatever it produces into JSON-safe data.

This module is imported both by the live addon and by headless Blender jobs, so
that a script behaves identically no matter which way it reaches Blender. It must
not import anything outside the standard library and ``bpy``/``mathutils``.
"""

from __future__ import annotations

import contextlib
import io
import math
import sys
import traceback

MAX_DEPTH = 6
MAX_ITEMS = 200
MAX_STRING = 20_000
MAX_STDOUT = 40_000

_MATHUTILS_TYPES = frozenset({"Vector", "Matrix", "Euler", "Quaternion", "Color", "bpy_prop_array"})


def _clip(text: str, limit: int = MAX_STRING) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"... [{len(text) - limit} more characters]"


def _describe(value: object) -> object:
    """Summarise a Blender datablock or any other opaque object."""
    rna = getattr(value, "bl_rna", None)
    if rna is not None:
        summary = {"__blender__": getattr(rna, "identifier", type(value).__name__)}
        name = getattr(value, "name", None)
        if isinstance(name, str):
            summary["name"] = name
        return summary
    return _clip(repr(value), 500)


def to_jsonable(value: object, depth: int = 0) -> object:
    """Best-effort conversion of arbitrary Blender values into JSON primitives."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        # JSON has no way to spell nan/inf, so keep them as readable strings.
        return value if math.isfinite(value) else repr(value)
    if isinstance(value, str):
        return _clip(value)
    if isinstance(value, (bytes, bytearray)):
        return f"<{len(value)} bytes>"

    if depth >= MAX_DEPTH:
        return _describe(value)

    if isinstance(value, dict):
        items = list(value.items())[:MAX_ITEMS]
        return {str(key): to_jsonable(item, depth + 1) for key, item in items}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item, depth + 1) for item in list(value)[:MAX_ITEMS]]

    type_name = type(value).__name__
    if type_name in _MATHUTILS_TYPES or type_name == "bpy_prop_collection":
        try:
            return [to_jsonable(item, depth + 1) for item in list(value)[:MAX_ITEMS]]
        except TypeError:
            pass

    return _describe(value)


def build_globals(extra: dict | None = None) -> dict:
    """Namespace handed to user scripts: bpy plus the shortcuts artists expect."""
    import bpy
    import mathutils

    namespace = {
        "__name__": "__blender_mcp__",
        "bpy": bpy,
        "mathutils": mathutils,
        "math": math,
        "D": bpy.data,
        "C": bpy.context,
    }
    if extra:
        namespace.update(extra)
    return namespace


def run_code(code: str, extra_globals: dict | None = None) -> dict:
    """Execute ``code`` and report its output, emitted values and final ``result``.

    A script communicates back in two ways: it may call ``emit(value)`` any number
    of times, and it may leave a variable named ``result`` bound at module level.
    """
    emitted: list = []
    namespace = build_globals(extra_globals)
    namespace["emit"] = emitted.append

    captured = io.StringIO()
    error = None
    try:
        compiled = compile(code, "<blender-mcp>", "exec")
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            exec(compiled, namespace)
    except Exception:
        error = _format_error()

    response = {
        "ok": error is None,
        "stdout": _clip(captured.getvalue(), MAX_STDOUT),
        "emitted": [to_jsonable(item) for item in emitted],
    }
    if error is not None:
        response["error"] = error
    if "result" in namespace:
        response["result"] = to_jsonable(namespace["result"])
    return response


def _format_error() -> str:
    """Traceback rewound to the user's script, hiding this module's exec frame."""
    exc_type, exc, tb = sys.exc_info()
    while tb is not None and tb.tb_frame.f_code.co_filename != "<blender-mcp>":
        tb = tb.tb_next
    return _clip("".join(traceback.format_exception(exc_type, exc, tb)), 8_000)
