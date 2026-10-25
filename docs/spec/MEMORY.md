# Persistence & Memory Specification

## Tables, Columns, and Indexes

| Table | Primary Columns | Indexes |
|---|---|---|
| `incidents` | `id`, `repo`, `workflow_id`, `run_id`, `traceback`, `status`, `created_at` | `idx_repo_run`, `idx_status` |
| `recovery_runs` | `id`, `incident_id`, `start_time`, `end_time`, `final_status` | `idx_incident_id` |
| `patch_outcomes` | `id`, `run_id`, `file_path`, `patch_hash`, `llm_latency`, `tokens` | `idx_run_id`, `idx_patch_hash` |
| `verification_runs` | `id`, `patch_id`, `type` (RED/GREEN), `stdout`, `exit_code` | `idx_patch_id` |
| `risk_decisions` | `id`, `patch_id`, `score`, `risk_level`, `factors` (JSONB) | `idx_patch_level` |
| `approvals` | `id`, `decision_id`, `user_id`, `approved_at`, `notes` | `idx_decision_id` |
| `regressions` | `id`, `pr_id`, `merge_sha`, `post_merge_stdout`, `status` | `idx_pr_id` |
| `patterns` | `id`, `error_signature`, `precedent_patch_hash`, `successes`, `attempts` | `idx_error_sig` |

## Ingestion & Deduplication
- **Ingestion Rule:** New `workflow_run` delivery payloads trigger row creation in `incidents` if `conclusion` is failure.
- **Dedupe Key:** Composite of `repository` + `workflow_id` + `run_id` + `job_id`. Attempts to re-ingest an identical run are dropped.

## Analytics & Learning
- **Confidence Formula:** `(successes / attempts) * 100` constrained to runs where `post_merge_verification == RESOLVED`. Never relies on self-reported LLM confidence.
- **Retrieval:** If `incidents.traceback` matches a known `patterns.error_signature`, inject the `precedent_patch_hash` text into the LLM prompt under `<PREVIOUS_SUCCESS>`.
- **Analytics Derivation:** 
  - `total_fixes`: Count of `recovery_runs` where `final_status == RESOLVED`.
  - `total_cost_saved_usd`: `total_fixes` * $500.
  - `mttr_reduction`: Average duration between `incidents.created_at` and `regressions.approved_at` across RESOLVED runs.
- **Seed-Data Migration:** All pre-existing seeded data in the database MUST have an `is_seed = true` flag. These are filtered out of all production analytic endpoints unless specifically toggled.

## Data Redaction & NEVER-STORE List
**NEVER-STORE List:**
- GitHub OAuth Tokens / PATs
- Nebius API Keys
- Webhook HMAC Secrets
- `.env` file contents pulled from repositories

**Redaction Spec:**
Prior to persisting `traceback`, `stdout`, or `stderr`, regex filters scrub substrings matching `/ghp_[a-zA-Z0-9]{36}/` and any sequence prefixed by `Authorization: Bearer`. 

**Planted-Fake-Secret Test:**
*Test Execution:* A failing test logs: `Crash connecting to DB: API_KEY=ghp_fake123abc456def789ghi012jkl345mno67`. 
*Expected Outcome:* The DB row in `incidents.traceback` strictly persists: `Crash connecting to DB: API_KEY=[REDACTED]`.

## Retention Policy
- `incidents` and `recovery_runs`: 365 days.
- `verification_runs` (heavy stdout): 30 days.
- `patterns` (successful signatures): Infinite (learning foundation).
