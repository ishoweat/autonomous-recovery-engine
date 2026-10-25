from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)


# ── Known bug patterns & signatures ──────────────────────────────────────────

ZERO_DIVISION_TRACE = """ZeroDivisionError: division by zero
Traceback (most recent call last):
  File "{file_path}", line {line}, in {func_name}
    {line_content}
ZeroDivisionError: division by zero"""

KEY_ERROR_TRACE = """KeyError: '{key_name}'
Traceback (most recent call last):
  File "{file_path}", line {line}, in {func_name}
    {line_content}
KeyError: '{key_name}'"""

SYNTAX_ERROR_TRACE = """SyntaxError: {msg}
  File "{file_path}", line {line}
    {line_content}
SyntaxError: {msg}"""

GENERIC_ERROR_TRACE = """RuntimeError: Detected unhandled defect in `{file_path}`
Traceback (most recent call last):
  File "{file_path}", line {line}, in {func_name}
    {line_content}
RuntimeError: Unhandled exception during execution"""


def scan_file_for_errors(
    file_path: str,
    content: str = "",
    recent_ci_traces: Optional[dict[str, str]] = None,
) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    Fast static/syntax and runtime defect inspection for a code file.

    Returns:
        (has_error, error_badge, error_context)
    """
    clean_path = file_path.strip("/")
    base_name = Path(clean_path).name

    # 1. Match against recent CI / test failure traces if provided
    if recent_ci_traces:
        for trace_key, trace_text in recent_ci_traces.items():
            if (
                trace_key == clean_path
                or trace_key == base_name
                or trace_key.endswith("/" + base_name)
                or clean_path.endswith("/" + trace_key)
            ):
                return True, "error", trace_text.strip()

    # Skip non-code files from deep scanning
    ext = Path(clean_path).suffix.lower()
    code_extensions = {".py", ".pyw", ".js", ".jsx", ".ts", ".tsx", ".go", ".rs", ".java"}
    if ext not in code_extensions:
        return False, None, None

    if not content.strip():
        return False, None, None

    # 2. Python-specific AST Syntax Check
    if ext in {".py", ".pyw"}:
        try:
            ast.parse(content)
        except SyntaxError as err:
            trace = SYNTAX_ERROR_TRACE.format(
                msg=err.msg,
                file_path=clean_path,
                line=err.lineno or 1,
                line_content=(err.text or "").strip() or "Syntax error in source code",
            )
            return True, "error", trace

    # 3. Bug pattern heuristics across lines
    lines = content.splitlines()

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()

        # Bug Pattern A: ZeroDivisionError
        # e.g., 'return total / len(numbers)' without len/numbers check
        if "/ len(" in stripped and "if " not in stripped and "len(" in stripped:
            # Check if previous lines guard against empty collection
            prev_context = "\n".join(lines[max(0, idx - 8):idx])
            if "if not " not in prev_context and "if len(" not in prev_context:
                func_name = _find_enclosing_function(lines, idx)
                trace = ZERO_DIVISION_TRACE.format(
                    file_path=clean_path,
                    line=idx,
                    func_name=func_name,
                    line_content=stripped,
                )
                return True, "error", trace

        # e.g., 'return a / b' without 'if b == 0:' check
        if re.search(r"return\s+[a-zA-Z0-9_]+\s*/\s*[a-zA-Z0-9_]+", stripped):
            prev_context = "\n".join(lines[max(0, idx - 6):idx])
            if "if " not in prev_context and "==" not in prev_context and "!=" not in prev_context:
                func_name = _find_enclosing_function(lines, idx)
                trace = ZERO_DIVISION_TRACE.format(
                    file_path=clean_path,
                    line=idx,
                    func_name=func_name,
                    line_content=stripped,
                )
                return True, "error", trace

        # Bug Pattern B: KeyError
        # Direct dictionary access e.g., payload["user_id"] without .get() or in check
        dict_match = re.search(r'(\b[a-zA-Z0-9_]+)\["([a-zA-Z0-9_]+)"\]', stripped)
        if dict_match and "test" not in clean_path.lower():
            var_name, key_name = dict_match.group(1), dict_match.group(2)
            prev_context = "\n".join(lines[max(0, idx - 6):idx])
            if f'"{key_name}" in' not in prev_context and f"'{key_name}' in" not in prev_context:
                func_name = _find_enclosing_function(lines, idx)
                trace = KEY_ERROR_TRACE.format(
                    key_name=key_name,
                    file_path=clean_path,
                    line=idx,
                    func_name=func_name,
                    line_content=stripped,
                )
                return True, "error", trace

        # Bug Pattern C: Explicit bug markers or comments
        if "# BUG:" in stripped or "# BUG" in stripped or "# defect" in stripped.lower():
            func_name = _find_enclosing_function(lines, idx)
            comment_text = stripped.split("#")[-1].strip()
            err_type = "ZeroDivisionError" if "zerodivision" in comment_text.lower() or "division" in comment_text.lower() else "RuntimeError"
            trace = f"""{err_type}: {comment_text}
Traceback (most recent call last):
  File "{clean_path}", line {idx}, in {func_name}
    {stripped}
{err_type}: {comment_text}"""
            return True, "error", trace

    # 4. JavaScript / TypeScript Bracket balancing check
    if ext in {".js", ".jsx", ".ts", ".tsx"}:
        stack = []
        pairs = {")": "(", "}": "{", "]": "["}
        for idx, line in enumerate(lines, start=1):
            for ch in line:
                if ch in ("(", "{", "["):
                    stack.append((ch, idx))
                elif ch in (")", "}", "]"):
                    if not stack or stack[-1][0] != pairs[ch]:
                        trace = f"""SyntaxError: Unexpected closing bracket `{ch}`
  File "{clean_path}", line {idx}
    {line.strip()}
SyntaxError: Unexpected `{ch}`"""
                        return True, "error", trace
                    stack.pop()
        if stack:
            open_ch, open_line = stack[-1]
            trace = f"""SyntaxError: Unclosed `{open_ch}` remaining
  File "{clean_path}", line {open_line}
SyntaxError: Unclosed bracket `{open_ch}`"""
            return True, "error", trace

    return False, None, None


def _find_enclosing_function(lines: list[str], target_line_idx: int) -> str:
    """Find the enclosing function name above target_line_idx."""
    for i in range(target_line_idx - 1, -1, -1):
        line = lines[i].strip()
        if line.startswith("def ") or line.startswith("async def "):
            match = re.search(r"def\s+([a-zA-Z0-9_]+)", line)
            if match:
                return match.group(1)
        elif line.startswith("function ") or "=>" in line:
            match = re.search(r"function\s+([a-zA-Z0-9_]+)", line)
            if match:
                return match.group(1)
    return "<module>"
