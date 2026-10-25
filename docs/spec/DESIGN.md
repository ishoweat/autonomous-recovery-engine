# UI & Design Specification

## Existing UI Inventory
- **Mission Control Layout:** Dark-mode dashboard with side navigation.
- **Components:** Incident Pipeline Strip, Diff Viewer, Sandbox Terminal Panel, Risk Gateway Card, GitHub PR Panel, Analytics Overview, Learning Report Table.

## Stage to Event Mapping

| UI Stage | Listening Event | Possible States |
|---|---|---|
| Ingestion & Context | `incident_ingested`, `target_resolved` | `idle`, `running`, `success`, `failed` |
| Nemotron Analysis | `patch_generation_started`, `inference_completed` | `idle`, `running`, `success`, `failed` |
| Patch Policy | `patch_policy_validated`, `tamper_attempted` | `skipped`, `success`, `blocked` |
| Sandbox RED/GREEN | `sandbox_started`, `sandbox_completed` | `idle`, `running`, `success`, `failed` |
| Risk Gate | `risk_evaluated` | `idle`, `success`, `awaiting-approval`, `blocked` |
| GitHub Check & PR | `pr_created` | `idle`, `running`, `success`, `failed` |
| Post-Merge | `merge_detected`, `incident_resolved` | `idle`, `running`, `success`, `failed` |

## Required Real-State UI Changes
- **Incident Card:** Drop "Trigger: Manual" default. Display exact `workflow_run` triggering event.
- **Target-File Badge:** Update badge dynamically based on backend resolver, not frontend local state.
- **Sandbox RED/GREEN:** Split sandbox view into side-by-side terminal panes. Left: Pre-patch RED (exit 1). Right: Post-patch GREEN (exit 0).
- **Patch-Policy Panel:** Show strict numbers: `SOURCE FILES CHANGED: [X], TEST/CI FILES CHANGED: [0]`.
- **Tamper-Blocked Banner:** A red alert banner (`BLOCKED: Adversarial LLM modification to protected test file`) that renders when `tamper_attempted` event fires.
- **Risk Breakdown:** Render JSONB `factors` array as bullet points (e.g., File Criticality: 0.35, Lines: 0.05).
- **Approval UI:** For MEDIUM risk, render a "Human Approval Required" action button.
- **Post-Merge & Evidence Drawer:** "MERGED" status transitions to a final "POST-MERGE: [PASS/FAIL]". Add "Download Evidence Bundle" button pulling JSON artifact.

## Loading, Empty, and Error States
- **Loading:** `[STAGE] Processing... (Elapsed: 00:00s)` using local interval timers synced to event start time.
- **Empty Analytics:** `No live data available.`
- **Error:** `Pipeline halted. Reason: [EVENT_MESSAGE]`.

## Honesty Labels & Presentation Mode
- **Honesty Labels:** All mocked or seeded metrics must carry a bright `[BENCHMARK]` or `[DEMO DATA]` tag adjacent to the metric.
- **Sandbox Provider Label:** Top right of the sandbox terminal must read `Provider: LocalDocker` (or `Provider: TokenFactory Sandbox` if verified).
- **Presentation Mode:** A global UI toggle that scales `rem` root font size up by 125% for recording clear demo videos.

## Vision Gap Table

| Element | Vision behavior | Real backend data source | Status | Required change |
|---|---|---|---|---|
| GITHUB FAILURE | UI shows GitHub CI exception/file | GitHub webhook payload (`workflow_run` logs) | MISSING | Parse raw logs for traceback. |
| TARGET FILE | Exact source file patched | `failure_file` from logs | MISSING | Map badge to dynamic `RecoveryState`. |
| SOURCE-ONLY | UI shows 0 Test files changed | Patch generator diff parser | MISSING | Extract test file blocklist metrics. |
| RED → GREEN | Run original test FAIL -> PASS | Pytest via Docker sandbox | MISSING | Capture two sandbox passes (pre/post). |
| RISK GATE | Calculate dynamic risk | `risk.py` diff parser | PARTIAL | Remove static scores; display factors array. |
| GITHUB CHECK | Report PASSED to Checks API | GitHub Checks API | MISSING | Update Check Runs upon RED->GREEN success. |
| PR / MERGE | PR merged state synced | GitHub `pull_request` webhook | MISSING | Add merge event listeners. |
| POST-MERGE | Checkout merge SHA & re-run tests | Webhook-triggered sandbox test | MISSING | Update UI state to RESOLVED/REGRESSION. |
| ANALYTICS | Live ROI calculation | Database `Incident` aggregation | LABELED-BENCHMARK | Add `[BENCHMARK]` tag or read true DB records. |

## Hardcode Removals
- Removed `"2 passed in 0.42s"` from `sandbox_node`.
- Removed static `0.05` base risk score.
- Removed fixed `49 incidents` and `$9,317 saved` UI defaults in favor of database aggregations or `[BENCHMARK]` labels.
