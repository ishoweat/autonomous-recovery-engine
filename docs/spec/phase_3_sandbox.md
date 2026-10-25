# Phase 3: Pre/Post Sandbox Verification (RED → GREEN)

## Objective
Verify the recovery patch by ensuring the original failing test is explicitly run before the patch is applied (FAIL) and after the patch is applied (PASS) inside the isolated Docker sandbox.

## Technical Requirements
1. **RED Verification (Baseline):**
   - Update `sandbox_node` in `backend/orchestration/nodes.py` to first execute the failing test suite (e.g. `pytest test_calculator.py`) *before* applying the generated diff.
   - Capture `stdout`, `stderr`, and confirm a non-zero `exit_code`.
2. **GREEN Verification (Post-Patch):**
   - Apply the patch.
   - Re-run the exact same test command.
   - Capture `stdout`, `stderr`, and confirm `exit_code == 0`.
3. **Data Persistence:**
   - Do not use hardcoded strings like "2 passed in 0.42s".
   - Persist both RED and GREEN execution outputs into the `test_results` field of `RecoveryState`.

## Acceptance Criteria
- `sandbox_node` explicitly validates failure prior to validating success.
- Both test runs reflect real pytest output in the UI.
