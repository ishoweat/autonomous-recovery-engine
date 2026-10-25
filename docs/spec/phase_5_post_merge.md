# Phase 5: Post-Merge Verification

## Objective
Implement a final verification stage that triggers after the recovery Pull Request is merged into the default branch, ensuring no regressions occurred and finalizing the incident state.

## Technical Requirements
1. **GitHub Pull Request Webhook:**
   - Update `backend/api/webhooks.py` to handle the `pull_request` event where `action == "closed"` and `merged == true`.
   - Identify the corresponding active `Incident` by PR number or branch.
2. **Post-Merge Execution:**
   - Fetch the exact `merge_commit_sha`.
   - Checkout this SHA within the `RecoverySandbox`.
   - Run the SAME original failing test suite.
3. **Status Resolution:**
   - If tests pass (exit code 0), mark the incident as `RESOLVED`.
   - If tests fail, mark the incident as `REGRESSION`.
   - Prevent the UI from sticking on "POST-MERGE: VERIFYING..." indefinitely.

## Acceptance Criteria
- Closing/Merging a PR natively on GitHub notifies the backend.
- The pipeline correctly runs post-merge tests.
- The UI reflects the final `RESOLVED` or `REGRESSION` state based on test outcome.
