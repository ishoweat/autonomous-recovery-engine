import pytest
from backend.services.universal_repair import (
    UniversalRepairEngine,
    detect_language_context,
    audit_patch_security,
    verify_code_syntax,
    run_stage_verification,
)


def test_multi_language_detection():
    """Verify language context detection across Python, TS, Go, Rust, Java."""
    # Python
    py_ctx = detect_language_context("backend/services/worker.py", "def work(): pass")
    assert py_ctx.language == "python"
    assert py_ctx.test_framework == "pytest"
    assert py_ctx.manifest_file == "pyproject.toml"

    # TypeScript
    ts_ctx = detect_language_context("src/components/Button.tsx", "export const Button = () => <div/>;")
    assert ts_ctx.language == "typescript"
    assert ts_ctx.test_framework == "jest"
    assert ts_ctx.manifest_file == "package.json"

    # Go
    go_ctx = detect_language_context("cmd/server/main.go", "package main\nfunc main() {}")
    assert go_ctx.language == "go"
    assert go_ctx.test_framework == "go test"
    assert go_ctx.manifest_file == "go.mod"

    # Rust
    rs_ctx = detect_language_context("src/lib.rs", "pub fn add(a: i32, b: i32) -> i32 { a + b }")
    assert rs_ctx.language == "rust"
    assert rs_ctx.test_framework == "cargo test"
    assert rs_ctx.manifest_file == "Cargo.toml"

    # Java
    java_ctx = detect_language_context("src/main/java/App.java", "public class App {}")
    assert java_ctx.language == "java"
    assert java_ctx.test_framework == "junit"
    assert java_ctx.manifest_file == "pom.xml"


def test_stage_1_syntax_checks():
    """Verify Stage 1 language-native syntax checks."""
    py_ctx = detect_language_context("script.py")
    valid_py = "def foo():\n    return 42\n"
    ok, err = verify_code_syntax(valid_py, py_ctx)
    assert ok is True
    assert err is None

    invalid_py = "def foo(\n    return 42"
    ok, err = verify_code_syntax(invalid_py, py_ctx)
    assert ok is False
    assert "SyntaxError" in str(err)

    # TypeScript unbalanced brackets
    ts_ctx = detect_language_context("app.ts")
    valid_ts = "function sum(a: number, b: number) { return a + b; }"
    ok, err = verify_code_syntax(valid_ts, ts_ctx)
    assert ok is True

    invalid_ts = "function sum(a: number, b: number) { return a + b;"
    ok, err = verify_code_syntax(invalid_ts, ts_ctx)
    assert ok is False
    assert "Unclosed" in str(err)


def test_stage_2_security_rejects_bare_catch_all():
    """Verify Stage 2 rejects bare catch-all error suppression."""
    orig = "def fetch(data):\n    return data['id']\n"
    # Bare catch-all: except Exception: pass
    bad_candidate = "def fetch(data):\n    try:\n        return data['id']\n    except Exception:\n        pass\n"
    patch_diff = "+    except Exception:\n+        pass"
    py_ctx = detect_language_context("fetcher.py")

    ok, violation = audit_patch_security(orig, bad_candidate, patch_diff, py_ctx)
    assert ok is False
    assert "Bare catch-all error suppression" in str(violation)

    # JavaScript empty catch: catch (e) {}
    orig_js = "function fetch(data) { return data.id; }"
    bad_js = "function fetch(data) { try { return data.id; } catch(e) {} }"
    js_ctx = detect_language_context("fetcher.js")
    ok_js, violation_js = audit_patch_security(orig_js, bad_js, "+ catch(e) {}", js_ctx)
    assert ok_js is False
    assert "Empty catch block" in str(violation_js)


def test_stage_2_security_rejects_test_deletion_or_tampering():
    """Verify Stage 2 rejects deletion of existing tests and skip decorators."""
    orig = "def test_calculate():\n    assert calculate(2, 2) == 4\n"
    bad_candidate = "# test deleted\n"
    patch_diff = "-def test_calculate():\n-    assert calculate(2, 2) == 4\n+# test deleted\n"
    py_ctx = detect_language_context("tests/test_calc.py")

    ok, violation = audit_patch_security(orig, bad_candidate, patch_diff, py_ctx)
    assert ok is False
    assert "Anti-tampering check detected deletion of existing test" in str(violation)

    # Reject adding @pytest.mark.skip
    skip_candidate = "@pytest.mark.skip\ndef test_calculate():\n    assert calculate(2, 2) == 4\n"
    patch_diff_skip = "+@pytest.mark.skip\n def test_calculate():"
    ok, violation = audit_patch_security(orig, skip_candidate, patch_diff_skip, py_ctx)
    assert ok is False
    assert "Added test-skipping annotation" in str(violation)


def test_stage_2_security_rejects_dangerous_calls_and_secrets():
    """Verify Stage 2 rejects dangerous calls (eval, exec, untrusted shell) and secrets."""
    orig = "def run_code(user_input):\n    return user_input.strip()\n"
    bad_eval = "def run_code(user_input):\n    return eval(user_input)\n"
    py_ctx = detect_language_context("evaluator.py")

    ok, violation = audit_patch_security(orig, bad_eval, "+    return eval(user_input)", py_ctx)
    assert ok is False
    assert "eval()" in str(violation)

    # Shell=True
    bad_shell = "def run_code(cmd):\n    import subprocess\n    subprocess.run(cmd, shell=True)\n"
    ok, violation = audit_patch_security(orig, bad_shell, "+ subprocess.run(cmd, shell=True)", py_ctx)
    assert ok is False
    assert "shell=True" in str(violation)

    # Hardcoded secrets
    bad_secret = 'API_KEY = "ghp_1234567890abcdefghijklmnopqrstuvwxyz1234"\n'
    ok, violation = audit_patch_security(orig, bad_secret, "+ API_KEY = 'ghp_...'", py_ctx)
    assert ok is False
    assert "hardcoded secret" in str(violation)


@pytest.mark.asyncio
async def test_stage_3_verification_pipeline():
    """Verify Stage 1, 2, 3 verification pipeline passes for valid patch."""
    orig = "def divide(a, b):\n    return a / b\n"
    fixed = (
        "def divide(a, b):\n"
        "    if b == 0:\n"
        "        raise ValueError('b cannot be zero')\n"
        "    return a / b\n"
    )
    lang_ctx = detect_language_context("calculator.py")
    targeted_test = "def test_divide_zero():\n    with pytest.raises(ValueError):\n        divide(10, 0)\n"

    result = await run_stage_verification(
        candidate_code=fixed,
        original_code=orig,
        file_path="calculator.py",
        lang_ctx=lang_ctx,
        targeted_test=targeted_test,
    )
    assert result.verified is True
    assert result.stage == "stage_3_sandbox_verified"
    assert result.exit_code == 0
    assert "passed" in result.stdout.lower()


@pytest.mark.asyncio
async def test_universal_repair_engine_success_deterministic():
    """Verify UniversalRepairEngine produces verified patch, test snippet, and safe risk score."""
    code = "def authenticate(payload):\n    user_id = payload['user_id']\n    return user_id\n"
    result = await UniversalRepairEngine.repair_and_verify(
        file_path="backend/api/auth.py",
        file_content=code,
        error_message="KeyError: 'user_id'",
        incident_id="inc-test-universal-01",
    )
    assert result.verified is True
    assert result.rolled_back is False
    assert result.status == "fixed"
    assert result.fixed_code != code
    assert "user_id" in result.fixed_code and ("get(" in result.fixed_code or "not in" in result.fixed_code or "in payload" in result.fixed_code or "raise" in result.fixed_code)
    assert result.targeted_test_code != ""
    assert result.risk_assessment["decision"] in ("BLOCK", "APPROVE")

    # Non-critical utility file should produce ALLOW
    code_calc = "def calculate_average(numbers):\n    total = sum(numbers)\n    return total / len(numbers)\n"
    res_calc = await UniversalRepairEngine.repair_and_verify(
        file_path="calculator.py",
        file_content=code_calc,
        error_message="ZeroDivisionError: division by zero",
        incident_id="inc-test-calc-01",
    )
    assert res_calc.verified is True
    assert res_calc.risk_assessment["decision"] in ("ALLOW", "APPROVE")
    assert result.test_results["tests_passed"] is True


@pytest.mark.asyncio
async def test_universal_repair_engine_rollback_on_failure(monkeypatch):
    """Verify UniversalRepairEngine rolls back cleanly to snapshot when verification fails."""
    code = "def process(item):\n    return item.value\n"

    # Simulate verification failure across all attempts
    async def mock_fail_verification(*args, **kwargs):
        from backend.services.universal_repair import VerificationResult
        return VerificationResult(
            stage="stage_2_security",
            verified=False,
            exit_code=1,
            stdout="",
            stderr="Security Gate Blocked",
            duration_seconds=0.05,
            violations=["Critical security violation detected"],
        )

    import backend.services.universal_repair as ur_module
    monkeypatch.setattr(ur_module, "run_stage_verification", mock_fail_verification)

    result = await UniversalRepairEngine.repair_and_verify(
        file_path="backend/services/process.py",
        file_content=code,
        error_message="AttributeError: 'NoneType' object has no attribute 'value'",
        incident_id="inc-test-universal-fail",
    )

    # Must cleanly roll back to original code
    assert result.verified is False
    assert result.rolled_back is True
    assert result.fixed_code == code
    assert result.status == "MANUAL_REVIEW_REQUIRED"
    assert result.attempts_made == UniversalRepairEngine.MAX_RETRIES + 1
    # Risk gateway must require human approval
    assert result.risk_assessment["decision"] == "APPROVE"
    assert result.risk_assessment["score"] >= 0.65
