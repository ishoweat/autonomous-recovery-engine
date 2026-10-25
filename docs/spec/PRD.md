# Product Requirements Document (PRD)
## Autonomous Recovery Engine (ARE)

## Problem & Pitch
**Problem:** CI/CD pipelines break frequently due to minor regressions, requiring manual triage, local reproduction, and context-switching which heavily impacts developer velocity.
**Pitch:** ARE is an autonomous, event-driven recovery engine that ingests GitHub CI failures, leverages NVIDIA Nemotron for root-cause analysis, sandboxes generated patches for validation, and issues safe, verified Pull Requests automatically.
**Differentiators:** Strict adversarial test-tampering protection, real RED/GREEN test verification inside isolated sandboxes, deterministic risk calculation blocking high-risk modifications, and zero direct pushes to `main`.

## Users
- **Maintainers:** Rely on ARE to reduce MTTR and merge safe, automated fixes.
- **Judges:** Evaluate the technical depth, agentic autonomy, adversarial robustness, and Token Factory integration of the hackathon submission.

## Current Capabilities (Audit Truth Table)
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

## Functional Requirements (FR-01..FR-13)
| ID | Requirement | Priority | Measurable Acceptance |
|---|---|---|---|
| FR-01 | Enforce Server-Side Tamper Protection | P0 | Diff parser blocks test, config, and CI modifications. |
| FR-02 | Dynamic Target Resolution | P0 | System resolves target file directly from fetched CI logs. |
| FR-03 | RED/GREEN Sandbox Verification | P0 | Original test executed pre-patch (fails) and post-patch (passes). |
| FR-04 | Event-Driven Architecture | P1 | Pipeline starts autonomously via verified GitHub webhook. |
| FR-05 | Risk Gate Calculation | P1 | Diff volume and file criticality determine LOW/MEDIUM/HIGH risk. |
| FR-06 | GitHub Check Runs | P1 | Commit status updated natively with pass/fail based on sandbox results. |
| FR-07 | Safe Pull Request Generation | P1 | PR opened against base branch with full RED/GREEN evidence. |
| FR-08 | Post-Merge Verification | P2 | Closing/Merging PR triggers validation run on the main branch. |
| FR-09 | True Analytics & Learning | P3 | Dashboard reflects only genuine, database-persisted incident data. |
| FR-10 | Benchmark Visual Labeling | P3 | UI explicitly tags pre-seeded demo data with `[BENCHMARK]`. |
| FR-11 | Nebius Token Factory Execution | P0 | Patch generation handled exclusively by `NebiusNemotron`. |
| FR-12 | UI Event-Driven Alignment | P2 | Frontend states (RESOLVED, ALLOW, RED/GREEN) strictly mirror backend. |
| FR-13 | Presentation Mode | P4 | Larger UI text toggle added for recording demo videos. |

## Non-Goals
- No introduction of new agent types (e.g., proactive maintenance agents).
- No unnecessary frontend redesigns (preserve existing layout and styles).
- No multi-repository cross-PR dependency resolution.

## The Judge Test
**Pass Conditions:**
1. A failing GitHub Actions run starts ARE with no manual click.
2. Exact traceback + link to the real GitHub run are shown.
3. Resolved target file differs from the UI-selected one.
4. RED: real sandbox test output displayed.
5. Tamper attempt (LLM edits a test) is blocked live.
6. Patch -> GREEN with real output; no collateral failures.
7. Risk breakdown; LOW auto, MEDIUM waits for approval, HIGH blocked.
8. GitHub status/check posted on the commit.
9. PR contains evidence (root cause, hash, before/after, risk).
10. Merge -> post-merge verification -> RESOLVED; analytics increments by 1.

## Track Fit & Stage Criteria
**Track:** Coding and Agentic Engineering
**Official Rules:** `UNVERIFIED — REQUIRES REPOSITORY INSPECTION` for official URL.
- **Stage 1 (Eligibility):** Open source, utilizes NVIDIA models via Nebius Token Factory.
- **Stage 2 Criteria 1 (Technical Implementation):** Robust server-side sandbox isolation, strict test-gaming protections, and deterministic LangGraph architecture.
- **Stage 2 Criteria 2 (Innovation):** Differentiating true agentic coding from mere code-generation by enforcing the RED -> GREEN paradigm automatically.
- **Stage 2 Criteria 3 (Impact/Usefulness):** Measurable reduction in MTTR by autonomously producing safe, evidence-backed Pull Requests.
- **Stage 2 Criteria 4 (Presentation):** Real-time, event-driven visualization via SSE streams in the Mission Control UI.

## Benchmark Success Metrics
- **Success Rate:** Pass@1 percentage for autonomous bug resolution (real runs only).
- **Latency:** Average time from webhook receipt to PR creation (real runs only).
- **Tamper Rejection Rate:** 100% block rate for adversarial LLM test modifications.
- **Token Efficiency:** Average input/output tokens consumed per resolution (real runs only).

## Risks
- **Sandbox Access:** Lack of native Token Factory execution sandboxing limits architecture to Docker.
- **GitHub App Setup Time:** Transitioning from OAuth to GitHub App for Check Runs API may introduce configuration delays.
- **Nemotron Latency:** Potential API timeouts during complex reasoning phases.
- **Flaky Tests:** Non-deterministic tests natively failing the GREEN verification.
- **Judge Login:** Ensuring judges have correct OAuth/sandbox permissions during live evaluation.
