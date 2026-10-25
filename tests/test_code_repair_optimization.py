from __future__ import annotations

import ast
import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.services.code_cleaner import (
    strip_markdown_fences,
    decode_escaped_newlines,
    preserve_original_structure,
    validate_and_clean_code,
)
from backend.services.http_client import get_shared_client
from backend.llm.nebius import create_nebius_client


def test_strip_markdown_fences():
    """Verify markdown fences and conversational wrappers are stripped cleanly."""
    raw_with_fences = "```python\ndef add(a: int, b: int) -> int:\n    return a + b\n```"
    cleaned = strip_markdown_fences(raw_with_fences)
    assert cleaned == "def add(a: int, b: int) -> int:\n    return a + b"

    raw_with_prose = (
        "Here is the fixed code:\n```python\ndef sub(a, b):\n    return a - b\n```\nHope this helps!"
    )
    cleaned = strip_markdown_fences(raw_with_prose)
    assert cleaned == "def sub(a, b):\n    return a - b"


def test_decode_escaped_newlines_never_flattened():
    """Verify double-escaped newlines (\\\\n) are decoded into real line breaks."""
    flattened = "import os\\ndef get_env():\\n    return os.getenv('KEY')\\n"
    decoded = decode_escaped_newlines(flattened)
    assert "\n" in decoded
    assert "\\n" not in decoded
    lines = decoded.splitlines()
    assert len(lines) >= 2
    assert lines[0] == "import os"
    assert lines[1] == "def get_env():"


def test_preserve_original_structure_and_imports():
    """Verify top-level imports and module docstrings from original code are preserved."""
    original = (
        "from __future__ import annotations\n"
        "from typing import List, Optional\n"
        "import math\n\n"
        "def calculate(vals: List[float]) -> float:\n"
        "    return sum(vals)\n"
    )
    # LLM returned only the function body omitting imports
    partial_fixed = (
        "def calculate(vals: List[float]) -> float:\n"
        "    if not vals:\n"
        "        return 0.0\n"
        "    return sum(vals)\n"
    )

    preserved = preserve_original_structure(partial_fixed, original)
    assert "from __future__ import annotations" in preserved
    assert "from typing import List, Optional" in preserved
    assert "import math" in preserved
    assert "def calculate" in preserved


def test_validate_and_clean_code_valid_and_invalid():
    """Verify ast.parse validation and auto-cleaning."""
    # 1. Valid code wrapped in fences and escaped newlines
    raw = "```python\ndef compute(x):\\n    return x * 2\n```"
    cleaned, is_valid, err = validate_and_clean_code(raw)
    assert is_valid is True
    assert err is None
    parsed = ast.parse(cleaned)
    assert isinstance(parsed, ast.Module)

    # 2. Syntax error that cannot be parsed
    broken = "def broken_func(:\n    return 1"
    cleaned_broken, is_valid, err = validate_and_clean_code(broken)
    assert is_valid is False
    assert err is not None
    assert "line" in err.lower() or "syntax" in err.lower() or "expected" in err.lower()


def test_persistent_shared_http_client():
    """Verify get_shared_client returns the same persistent AsyncClient."""
    c1 = get_shared_client()
    c2 = get_shared_client()
    assert c1 is c2
    assert not c1.is_closed


def test_nebius_client_caching():
    """Verify create_nebius_client reuses the pooled instance across calls."""
    llm1 = create_nebius_client()
    llm2 = create_nebius_client()
    assert llm1 is llm2


@pytest.mark.asyncio
async def test_code_repair_endpoint_single_pass_mock():
    """Verify POST /api/v1/incident/{incident_id}/repair returns valid schema and clean code."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "code": "def authenticate(payload):\n    user_id = payload['user_id']\n    return user_id\n",
            "file_path": "backend/api/auth.py",
            "language": "python",
            "error_message": "KeyError: 'user_id'",
        }
        res = await client.post("/api/v1/incident/inc_test_speed_001/repair", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert data["incident_id"] == "inc_test_speed_001"
        assert data["corrected_code"] != payload["code"]
        assert data["status"] == "fixed"
        assert "diff" in data["patch_diff"] or "auth.py" in data["patch_diff"]

        # Validate that the returned corrected code is 100% syntactically valid Python
        ast.parse(data["corrected_code"])


@pytest.mark.asyncio
async def test_remediate_endpoint_clean_code_and_ast():
    """Verify POST /api/remediate cleans code and produces 100% syntactically valid AST."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "filePath": "calculator.py",
            "fileContent": "def calculate_average(numbers):\n    total = sum(numbers)\n    return total / len(numbers)\n",
            "errorMessage": "ZeroDivisionError: division by zero",
            "stackTrace": "ZeroDivisionError: division by zero",
        }
        res = await client.post("/api/remediate", json=payload)
        assert res.status_code == 200
        data = res.json()
        assert "fixedCode" in data
        assert "diff" in data
        assert data["testResults"]["tests_passed"] is True
        assert data["riskAssessment"]["decision"] == "ALLOW"

        # Validate syntax of returned fix
        ast.parse(data["fixedCode"])


@pytest.mark.asyncio
async def test_create_pr_rejects_syntax_errors():
    """Verify POST /api/github/create-pr rejects invalid Python code before push."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "repo": "demo/autonomous-recovery-engine",
            "filePath": "calculator.py",
            "fixedContent": "def invalid_python(:\n    return False\n",
            "commitMessage": "broken syntax commit",
        }
        res = await client.post("/api/github/create-pr", json=payload)
        assert res.status_code == 422
        assert "syntax error" in res.json()["detail"].lower()
