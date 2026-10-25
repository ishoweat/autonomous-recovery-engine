# Phase 4: Risk Gate & GitHub Integration (Checks & PR)

## Objective
Dynamically calculate the risk of the patch based on real diff properties, update the commit status via GitHub Checks, and generate a descriptive Pull Request.

## Technical Requirements
1. **Risk Calculation:**
   - In `backend/orchestration/risk.py`, remove static assignments.
   - Parse the unified diff string to calculate `lines_added` and `lines_deleted`.
   - Calculate risk based on `files_changed`, security paths, and diff volume.
2. **GitHub Checks API:**
   - Add a method in `backend/integrations/github_tools.py` to create/update a GitHub Check run.
   - Once the sandbox and risk gate pass, report "PASSED" to the original commit SHA.
3. **PR Creation:**
   - Update `create_recovery_pr` in `github_tools.py` or the PR node.
   - The PR body must include the dynamically generated root cause, actual RED/GREEN sandbox output, and the true computed risk score.

## Acceptance Criteria
- The Risk Gate correctly flags massive refactors or security file modifications.
- GitHub natively displays a PASSED check from the recovery engine.
- The PR description is accurate to the current incident and patch execution.
