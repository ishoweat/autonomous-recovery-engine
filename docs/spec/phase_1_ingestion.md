# Phase 1: Ingestion & Target Identification

## Objectives
- Normalize GitHub Actions webhook failure into a `RecoveryState` with exact traceback and file.

## Required Changes

| Component | Path:Line | Current State | Required Update |
|---|---|---|---|
| Webhook Log Fetching | `backend/services/github_webhook.py:172` | `parse_github_webhook` parses JSON payload only. | Add API call to `https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs` to fetch raw logs for failing jobs. |
| Incident Trigger | `backend/api/webhooks.py:150` | `incident_id` created, but missing traceback extraction. | Pass downloaded logs into `RecoveryState` initialization. |
| Target Identification | `backend/orchestration/state_factory.py:94` | Regex `r'File "([^"]+\.py)"'` assumes `error_message` is pre-populated in payload. | Update regex to parse downloaded GitHub Actions raw logs to set `failure_file`, `failure_line`, and `stack_trace`. |

## Acceptance Criteria
- [ ] Failing GitHub Actions workflow triggers webhook.
- [ ] Backend autonomously downloads workflow logs from GitHub API.
- [ ] Exact exception and target file are extracted into `RecoveryState`.
