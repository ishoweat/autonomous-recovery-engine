# Repository Implementation Audit

## Architecture & Entry Points
- **Backend:** FastAPI entry point at `backend/main.py`.
- **Run Command:** `uvicorn backend.main:app --reload`
- **Frontend:** Next.js application at `frontend/app/`.
- **Run Command:** `npm run dev`
- **Orchestration:** LangGraph state machine located in `backend/orchestration/nodes.py` and `backend/orchestration/runtime.py`.
- **SSE Events:** Triggered via `emit_node_event` (`backend/orchestration/telemetry.py`), consumed via `/api/v1/incidents/stream`.
- **Database:** PostgreSQL (SQLAlchemy models in `backend/db/models.py`), tracks `Incident` and `FixRecord`. Redis is not explicitly modeled for core state.

## Environments & Integrations
- **Env Var Names:** `GITHUB_TOKEN`, `GITHUB_WEBHOOK_SECRET`, `NEBIUS_API_KEY`, `DATABASE_URL`.
- **GitHub Auth Mode:** OAuth app pattern used via `backend/api/auth.py`. Scope verification (Check Runs require GitHub App) is currently unverified.
- **Nebius Client:** `NebiusNemotron` class in `backend/llm/nebius.py`, invokes `nemotron-4-340b-instruct`.
- **Prompts:** Located in `backend/orchestration/prompts.py`.
- **Sandbox execution:** Tests execute via Docker container spawned in `backend/sandbox/sandbox.py`.
- **Risk Gate:** `backend/orchestration/risk.py:26` (Currently uses static `CRITICAL_FILES`).

## (I) Fabrications & Hardcodes Found
- **Sandbox Output:** `backend/orchestration/nodes.py:1326` hardcodes `"================ 2 passed in 0.42s ================\n"`.
- **Risk Gate:** `backend/orchestration/risk.py:97` assigns static baseline risk (0.05).
- **Trigger:** Frontend `frontend/app/detect/page.tsx:525` dynamically uses whatever the backend sends, but the backend lacks webhook trace extraction, forcing manual triggers or mock flows.
- **Analytics:** The UI or `roi.py` fetches data, but benchmark data (49 incidents, $9,317, 98.2%) may be seeded in DB (`seed_db.py`).

## (J) Root Cause of PR #26 Test-File Edit
- **Cause:** `repair_node` (`backend/orchestration/nodes.py:930`) executes regex extraction of the LLM patch but applies NO server-side path filtering. It does not reject patches that alter `tests/` or `.py` test suites.

## (K) Truth Table of U1-U13 Upgrades
| Upgrade | Status | Evidence |
|---|---|---|
| U1 Test-tamper protection | MISSING | No filtering logic in `repair_node`. |
| U2 Real incident context | MISSING | Webhook handler `parse_github_webhook` doesn't fetch logs. |
| U3 Target-file resolver | MISSING | `state_factory.py` assumes payload has `error_message`. |
| U4 Real RED/GREEN verification | MISSING | Sandbox runs patch once, outputs hardcoded `"2 passed"`. |
| U5 Real webhook primary path | PARTIAL | Endpoint exists but skips payload verification & extraction. |
| U6 Deterministic risk gate | PARTIAL | `risk.py` exists but uses static volume logic. |
| U7 GitHub Checks API | MISSING | `GitHubTools` does not implement Check Runs API. |
| U8 Safe PR lifecycle | PARTIAL | PR is created via `github_pr.py`, but merge logic is decoupled. |
| U9 Post-merge verification | MISSING | No webhook listener for `pull_request` merged events. |
| U10 Honest analytics | PARTIAL | Endpoints exist, but data contains seeded benchmark stats. |
| U11 Persistent learning | PARTIAL | Duplicates and `test-org` records present in API responses. |
| U12 Nebius Sandboxing | PARTIAL | Uses Docker; official Nebius Sandbox API unverified. |
| U13 Frontend event-driven | PARTIAL | SSE events consumed, but some states are mocked if missing. |

## (L) VISION_NOTES UI Equivalents
- **Layout:** Mission Control dark mode exists.
- **Panels:** Diff, Sandbox, Risk, Analytics, Learning Report exist.
- **Metrics:** ROI, MTTR, Hours Saved UI widgets exist (populated via `/api/v1/roi`).
