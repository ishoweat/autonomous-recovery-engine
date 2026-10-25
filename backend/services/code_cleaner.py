from __future__ import annotations

import ast
import logging
import re
from typing import Tuple

logger = logging.getLogger(__name__)


def strip_markdown_fences(code: str) -> str:
    """
    Strip markdown code fences (e.g. ```python ... ``` or ``` ... ```)
    and any conversational preamble/postamble surrounding the code block.
    """
    if not code:
        return ""

    cleaned = code.strip()

    # 1. Match code blocks enclosed in ```lang ... ``` or ``` ... ```
    fence_pattern = re.compile(
        r"```[a-zA-Z0-9_\-\.\+]*\s*\n([\s\S]*?)\n```",
        re.IGNORECASE,
    )
    matches = fence_pattern.findall(cleaned)
    if matches:
        # Take the largest or last code block
        cleaned = matches[-1].strip()
    else:
        # If string starts or ends with backticks
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if len(lines) >= 2:
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()
        cleaned = re.sub(r"^```[a-zA-Z0-9_\-\.\+]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    return cleaned


def decode_escaped_newlines(code: str) -> str:
    """
    Detect and decode double-escaped newlines (\\\\n -> \\n) and related escapes
    so that the file is NEVER committed as a single flattened line.
    """
    if not code:
        return ""

    # Check for literal escaped newlines: "\\n"
    if "\\n" in code:
        actual_newlines = code.count("\n")
        escaped_newlines = code.count("\\n")

        # If code has very few actual newlines but many escaped newlines, or only a single line
        if actual_newlines <= 2 or escaped_newlines > actual_newlines:
            logger.info("Detected double-escaped newlines (%d occurrences); unescaping to real line breaks.", escaped_newlines)
            code = code.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "    ")
            code = code.replace('\\"', '"').replace("\\'", "'")

    return code


def preserve_original_structure(fixed_code: str, original_code: str) -> str:
    """
    Ensure the full corrected file preserves all original imports, docstrings,
    and structure if the LLM returned only a partial function or omitted imports.
    """
    if not original_code or not fixed_code:
        return fixed_code

    # Check if original code has top-level imports that fixed_code completely dropped
    orig_lines = original_code.splitlines()
    fixed_lines = fixed_code.splitlines()

    # Collect import lines from original code
    orig_imports: list[str] = []
    has_future = False
    for line in orig_lines:
        stripped = line.strip()
        if stripped.startswith("from __future__ import"):
            has_future = True
            orig_imports.append(line)
        elif stripped.startswith("import ") or stripped.startswith("from "):
            orig_imports.append(line)
        elif stripped and not stripped.startswith("#") and not stripped.startswith('"""') and not stripped.startswith("'''"):
            # Reached code body
            break

    # If original had imports, check if fixed_code has any imports
    fixed_has_imports = any(
        line.strip().startswith("import ") or line.strip().startswith("from ")
        for line in fixed_lines
    )

    if orig_imports and not fixed_has_imports:
        logger.info("Fixed code dropped all module imports from original code; restoring %d import lines.", len(orig_imports))
        import_block = "\n".join(orig_imports) + "\n\n"
        fixed_code = import_block + fixed_code.lstrip()
    elif has_future and "from __future__ import" not in fixed_code:
        # Guarantee __future__ import remains at the very top
        future_line = [line for line in orig_imports if "from __future__ import" in line][0]
        fixed_code = f"{future_line}\n" + fixed_code

    return fixed_code


def validate_and_clean_code(
    fixed_code: str,
    original_code: str = "",
) -> Tuple[str, bool, str | None]:
    """
    Clean extracted code (strip markdown fences, decode escaped newlines, preserve structure)
    and validate with ast.parse.

    Returns:
        (cleaned_code, is_valid_ast, syntax_error_message_if_any)
    """
    if not fixed_code:
        return ("", False, "Empty code provided.")

    cleaned = strip_markdown_fences(fixed_code)
    cleaned = decode_escaped_newlines(cleaned)
    if original_code:
        cleaned = preserve_original_structure(cleaned, original_code)

    if not cleaned.endswith("\n"):
        cleaned += "\n"

    # AST validation pass 1
    try:
        ast.parse(cleaned)
        return (cleaned, True, None)
    except SyntaxError as first_err:
        logger.warning("AST parse pass 1 failed: %s (line %s). Attempting auto-cleaning.", first_err.msg, first_err.lineno)

    # Auto-cleaning heuristics for common LLM syntax flaws
    lines = cleaned.splitlines()

    # Heuristic 1: Strip leading conversational lines before Python code starts
    filtered_lines: list[str] = []
    started = False
    for line in lines:
        stripped = line.strip()
        if not started:
            # Check if this line looks like valid start of Python code
            if (
                stripped.startswith("from ")
                or stripped.startswith("import ")
                or stripped.startswith("def ")
                or stripped.startswith("class ")
                or stripped.startswith("#")
                or stripped.startswith('"""')
                or stripped.startswith("'''")
                or stripped.startswith("@")
            ):
                started = True
                filtered_lines.append(line)
            # Else skip conversational prefix (e.g. "Here is the corrected code:")
            continue
        filtered_lines.append(line)

    if filtered_lines and filtered_lines != lines:
        candidate = "\n".join(filtered_lines) + "\n"
        try:
            ast.parse(candidate)
            logger.info("Auto-cleaning succeeded by trimming conversational prefix.")
            return (candidate, True, None)
        except SyntaxError:
            pass

    # Heuristic 2: Strip trailing conversational lines or stray markdown backticks
    while lines and (
        lines[-1].strip().startswith("```")
        or lines[-1].strip().startswith("Hope ")
        or lines[-1].strip().startswith("Note:")
        or lines[-1].strip().startswith("This fix ")
    ):
        lines.pop()

    candidate = "\n".join(lines) + "\n"
    try:
        ast.parse(candidate)
        logger.info("Auto-cleaning succeeded by trimming conversational suffix.")
        return (candidate, True, None)
    except SyntaxError as final_err:
        err_msg = f"{final_err.msg} at line {final_err.lineno}"
        return (cleaned, False, err_msg)
