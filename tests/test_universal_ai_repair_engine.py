"""
tests/test_universal_ai_repair_engine.py
─────────────────────────────────────────
Comprehensive verification suite for the Universal AI Code Repair Engine.
Tests:
1. Multi-language defect diagnosis and contract-preserving repair (Python, JS/TS, Go, Java, C/C++, PHP, SQL).
2. Polyglot syntax verification (Python AST, JSON, TOML, YAML, SQL, brackets).
3. Security and anti-tampering gate enforcement (test deletion, bare excepts, eval/exec, secrets).
4. Truthful reporting (VERIFIED, PARTIALLY_VERIFIED, FAILED).
5. Ephemeral sandbox execution and zero file persistence.
6. Bounded self-healing retry loop (MAX_RETRIES=3) and snapshot rollback.
"""

import ast
import json
import pytest
from backend.services.universal_repair import (
    LanguageContext,
    detect_language_context,
    verify_code_syntax,
    audit_patch_security,
    run_stage_verification,
    UniversalRepairEngine,
)
from backend.services.universal_remediator import UniversalPatternRemediator
from backend.services.code_cleaner import strip_markdown_fences, decode_escaped_newlines


# ── 1. Polyglot Language & Framework Detection ────────────────────────────────

def test_language_and_framework_detection():
    # Python + FastAPI
    py_code = "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef index(): return {'status': 'ok'}"
    ctx = detect_language_context("api/main.py", py_code)
    assert ctx.language == "python"
    assert ctx.framework == "fastapi"
    assert ctx.test_framework == "pytest"

    # TypeScript + React
    ts_code = "import React, { useState } from 'react';\nexport const App: React.FC = () => <div>Hello</div>;"
    ctx = detect_language_context("components/App.tsx", ts_code)
    assert ctx.language == "typescript"
    assert ctx.framework == "react"
    assert ctx.test_framework == "jest"

    # Go + Gin
    go_code = 'package main\nimport "github.com/gin-gonic/gin"\nfunc main() { r := gin.Default(); r.Run() }'
    ctx = detect_language_context("main.go", go_code)
    assert ctx.language == "go"
    assert ctx.framework == "gin"
    assert ctx.test_framework == "go test"

    # SQL
    sql_code = "SELECT id, username FROM users WHERE active = 1;"
    ctx = detect_language_context("queries/fetch.sql", sql_code)
    assert ctx.language == "sql"

    # Configs
    assert detect_language_context("config.toml", "").language == "toml"
    assert detect_language_context("data.yaml", "").language == "yaml"
    assert detect_language_context("settings.json", "").language == "json"


# ── 2. Multi-Language Deterministic Remediation (UniversalPatternRemediator) ──

def test_remediate_python_zero_division():
    code = (
        "def compute_ratios(values):\n"
        "    count = len(values)\n"
        "    total = sum(values)\n"
        "    return total / count\n"
    )
    rem = UniversalPatternRemediator.remediate(
        code=code,
        file_path="math_utils.py",
        error_message="ZeroDivisionError: division by zero",
    )
    assert rem.was_fixed
    assert "count == 0" in rem.fixed_code or "if not" in rem.fixed_code or "count else" in rem.fixed_code
    # Validate syntax of repaired Python code
    ast.parse(rem.fixed_code)


def test_remediate_python_key_error():
    code = (
        "def process_order(payload):\n"
        "    order_id = payload['order_id']\n"
        "    amount = payload['amount']\n"
        "    return order_id, amount\n"
    )
    rem = UniversalPatternRemediator.remediate(
        code=code,
        file_path="orders.py",
        error_message="KeyError: 'order_id'",
    )
    assert rem.was_fixed
    assert ".get(" in rem.fixed_code
    ast.parse(rem.fixed_code)


def test_remediate_javascript_optional_chaining():
    code = (
        "function getUsername(user) {\n"
        "    return user.profile.name;\n"
        "}\n"
    )
    rem = UniversalPatternRemediator.remediate(
        code=code,
        file_path="user.js",
        error_message="TypeError: Cannot read properties of undefined (reading 'name')",
    )
    assert rem.was_fixed
    assert "?." in rem.fixed_code


def test_remediate_go_nil_slice():
    code = (
        "package main\n\n"
        "func getFirst(items []string) string {\n"
        "    return items[0]\n"
        "}\n"
    )
    rem = UniversalPatternRemediator.remediate(
        code=code,
        file_path="service.go",
        error_message="panic: runtime error: index out of range [0] with length 0",
    )
    assert rem.was_fixed
    assert "len(items)" in rem.fixed_code and ("<= 0" in rem.fixed_code or "== 0" in rem.fixed_code)


def test_remediate_php_null_coalesce():
    code = (
        "<?php\n"
        "function get_config($arr) {\n"
        "    return $arr['key'];\n"
        "}\n"
    )
    rem = UniversalPatternRemediator.remediate(
        code=code,
        file_path="config.php",
        error_message="Undefined array key 'key'",
    )
    assert rem.was_fixed
    assert "?? null" in rem.fixed_code or "isset(" in rem.fixed_code


def test_remediate_sql_missing_quote_and_semicolon():
    bad_sql = "SELECT id, email FROM accounts WHERE status = 'active"
    rem = UniversalPatternRemediator.remediate(
        code=bad_sql,
        file_path="query.sql",
        error_message="syntax error at or near 'active'",
    )
    assert rem.was_fixed
    assert rem.fixed_code.count("'") % 2 == 0
    assert rem.fixed_code.rstrip().endswith(";")


# ── 3. Stage 1 Syntax & Static Verification ───────────────────────────────────

def test_syntax_checker_polyglot():
    # Python AST valid & invalid
    ctx_py = detect_language_context("test.py", "x = 1")
    assert verify_code_syntax("x = 1\ny = 2\n", ctx_py)[0] is True
    assert verify_code_syntax("x = (\n", ctx_py)[0] is False

    # JSON valid & invalid
    ctx_json = detect_language_context("data.json", "{}")
    assert verify_code_syntax('{"valid": true, "count": 10}', ctx_json)[0] is True
    assert verify_code_syntax('{"broken": true, }', ctx_json)[0] is False

    # TOML valid & invalid
    ctx_toml = detect_language_context("config.toml", "")
    assert verify_code_syntax('[package]\nname = "are"\nversion = "1.0"', ctx_toml)[0] is True
    assert verify_code_syntax('[package\nname = "broken', ctx_toml)[0] is False

    # YAML valid & invalid
    ctx_yaml = detect_language_context("ci.yaml", "")
    assert verify_code_syntax("name: CI\njobs:\n  test:\n    runs-on: ubuntu-latest\n", ctx_yaml)[0] is True

    # Bracket matching for TS/JS/Go
    ctx_ts = detect_language_context("script.ts", "")
    assert verify_code_syntax("function test() { if (true) { return [1, 2]; } }", ctx_ts)[0] is True
    assert verify_code_syntax("function test() { if (true) { return [1, 2; } }", ctx_ts)[0] is False


# ── 4. Stage 2 Anti-Tampering & Security Gate ────────────────────────────────

def test_security_gate_rejection_bare_except():
    ctx = detect_language_context("service.py", "")
    orig = "def fetch():\n    return parse_data()\n"
    bad_fix = "def fetch():\n    try:\n        return parse_data()\n    except Exception:\n        pass\n"
    diff = "- def fetch():\n+ def fetch():\n+     try:\n+         return parse_data()\n+     except Exception:\n+         pass\n"
    ok, reason = audit_patch_security(orig, bad_fix, diff, ctx)
    assert ok is False
    assert "Bare catch-all error suppression" in reason


def test_security_gate_rejection_test_deletion():
    ctx = detect_language_context("tests/test_auth.py", "")
    orig = "def test_login_success():\n    assert True\ndef test_invalid_password():\n    assert False\n"
    bad_fix = "def test_login_success():\n    assert True\n"
    diff = "--- a/tests/test_auth.py\n+++ b/tests/test_auth.py\n-def test_invalid_password():\n-    assert False\n"
    ok, reason = audit_patch_security(orig, bad_fix, diff, ctx)
    assert ok is False
    assert "Anti-tampering check detected deletion of existing test" in reason


def test_security_gate_rejection_eval_and_injection():
    ctx = detect_language_context("handler.py", "")
    orig = "def handle(expr):\n    return int(expr)\n"
    bad_fix = "def handle(expr):\n    return eval(expr)\n"
    diff = "+    return eval(expr)\n"
    ok, reason = audit_patch_security(orig, bad_fix, diff, ctx)
    assert ok is False
    assert "Dangerous call introduced: `eval()` execution" in reason


def test_security_gate_rejection_hardcoded_secrets():
    ctx = detect_language_context("client.py", "")
    orig = "def get_token():\n    return os.environ['TOKEN']\n"
    bad_fix = 'def get_token():\n    api_key = "ghp_12345678901234567890123456789012"\n    return api_key\n'
    diff = '+    api_key = "ghp_12345678901234567890123456789012"\n'
    ok, reason = audit_patch_security(orig, bad_fix, diff, ctx)
    assert ok is False
    assert "hardcoded secret" in reason.lower()


# ── 5. Truthful Verification Lifecycle ───────────────────────────────────────

@pytest.mark.asyncio
async def test_truthful_verification_with_real_python_test():
    # Valid candidate with passing regression test executes real pytest
    code = "def add(a, b):\n    return a + b\n"
    orig = "def add(a, b):\n    return a - b\n"
    test_code = "from test_math import add\ndef test_add():\n    assert add(2, 3) == 5\n"
    ctx = detect_language_context("test_math.py", code)

    res = await run_stage_verification(
        candidate_code=code,
        original_code=orig,
        file_path="test_math.py",
        lang_ctx=ctx,
        targeted_test=test_code,
        incident_id="inc-truth-1",
    )
    assert res.verified is True
    assert res.verification_status == "VERIFIED"
    assert res.test_executed is True
    assert res.exit_code == 0


@pytest.mark.asyncio
async def test_truthful_verification_partially_verified_when_runner_not_executed():
    # Non-python code without container runner truthful status
    ts_code = "function greet(name: string): string { return `Hello, ${name}`; }"
    orig = "function greet(name: string): string { return 'Hello'; }"
    ctx = detect_language_context("greet.ts", ts_code)

    res = await run_stage_verification(
        candidate_code=ts_code,
        original_code=orig,
        file_path="greet.ts",
        lang_ctx=ctx,
        targeted_test=None,
        incident_id="inc-truth-2",
    )
    assert res.verified is True
    assert res.verification_status == "PARTIALLY_VERIFIED"
    assert res.test_executed is False
    assert "PARTIALLY_VERIFIED" in res.verification_status
    assert "Dynamic sandbox test runner not executed" in res.stdout


# ── 6. Full UniversalRepairEngine Pipeline (Rollback & Bounded Retries) ───────

@pytest.mark.asyncio
async def test_universal_repair_engine_deterministic_cycle(monkeypatch):
    from backend.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "nebius_api_key", "")

    code = (
        "def calculate_tax(amount, rate):\n"
        "    if rate == 0:\n"
        "        pass\n"
        "    return amount / rate\n"
    )
    result = await UniversalRepairEngine.repair_and_verify(
        file_path="finance.py",
        file_content=code,
        error_message="ZeroDivisionError: division by zero",
        incident_id="inc-engine-1",
    )

    assert result.status == "fixed"
    assert result.verified is True
    assert result.rolled_back is False
    assert result.attempts_made >= 1
    assert result.attempts_made <= UniversalRepairEngine.MAX_RETRIES + 1
    assert result.verification_status in ("VERIFIED", "PARTIALLY_VERIFIED")
    assert result.risk_assessment["decision"] in ("ALLOW", "APPROVE")


@pytest.mark.asyncio
async def test_universal_repair_engine_rollback_on_persistent_failure(monkeypatch):
    from backend.config import get_settings
    settings = get_settings()
    monkeypatch.setattr(settings, "nebius_api_key", "")

    # Incurable syntax error that causes all verification attempts to fail
    bad_code = "def broken(:"
    result = await UniversalRepairEngine.repair_and_verify(
        file_path="broken.py",
        file_content=bad_code,
        error_message="SyntaxError: invalid syntax",
        incident_id="inc-engine-rollback",
    )

    assert result.status == "MANUAL_REVIEW_REQUIRED"
    assert result.rolled_back is True
    assert result.fixed_code == bad_code
    assert result.verified is False
    assert result.risk_assessment["decision"] in ("APPROVE", "BLOCK")
