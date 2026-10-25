# Implementation Task Tracker

## Task Template Reference
*Each task uses the following format:*
`ID | Title | Objective | Inspect | Requirements | Dependencies | Acceptance | Done`

---

## Phases (Strict Order)

### P0: Safety, Correctness & De-fabrication
| ID | Title | Objective | Inspect | Requirements | Dependencies | Acceptance | Done |
|---|---|---|---|---|---|---|---|
| T0.1 | Remove Fabrications | Purge all hardcoded strings. | `backend/orchestration/nodes.py:1326`, `risk.py:97` | Remove `"2 passed in 0.42s"` and static risk scores. | None | `grep -r "0.42s"` returns empty. | [ ] |
| T0.2 | Diff Validator | Enforce test-tamper blocklist. | `nodes.py:repair_node` | Reject diffs editing `tests/**`, CI files, or containing `../`. | T0.1 | LLM attempt to edit test fails with `AdversarialRiskError`. | [ ] |
| T0.3 | Target Resolver | Identify exact source file. | `state_factory.py` | Parse stack frames to locate deepest non-test source. | T0.1 | Resolver picks `auth.py`, not `test_auth.py`. | [ ] |

### P1: Ingestion & Normalization
| ID | Title | Objective | Inspect | Requirements | Dependencies | Acceptance | Done |
|---|---|---|---|---|---|---|---|
| T1.1 | Webhook Logs | Fetch raw workflow logs. | `webhooks.py`, `github_webhook.py` | Download logs from GitHub Actions API. | P0 | Endpoint captures and parses full stack trace. | [ ] |
| T1.2 | Demo Repo Setup | Create reproducible trigger. | N/A | Create a repository with a deterministic failing GitHub Action. | None | Pushing bug triggers Action. | [ ] |

### P2: Real Sandbox
| ID | Title | Objective | Inspect | Requirements | Dependencies | Acceptance | Done |
|---|---|---|---|---|---|---|---|
| T2.1 | SandboxRunner Interface | Abstract sandbox execution. | `sandbox.py` | Define `SandboxRunner` and `LocalDockerRunner`. | P1 | Class interface cleanly separates docker commands. | [ ] |
| T2.2 | RED/GREEN Paradigm | Pre and post patch tests. | `nodes.py:sandbox_node` | Run test pre-patch (assert exit!=0), apply, run test post-patch (assert exit==0). | T2.1 | UI shows two real outputs: one failing, one passing. | [ ] |

### P3: Risk, Checks & PR
| ID | Title | Objective | Inspect | Requirements | Dependencies | Acceptance | Done |
|---|---|---|---|---|---|---|---|
| T3.1 | Dynamic Risk Config | Compute risk deterministically. | `risk.py` | Score based on diff line volume and config file list. | P2 | 2-line change -> LOW. 500-line change -> HIGH. | [ ] |
| T3.2 | GitHub Checks | Natively report Check Run. | `github_pr.py` | POST to Check Runs API with sandbox outcome. | T3.1 | GitHub UI shows green checkmark from ARE. | [ ] |
| T3.3 | Evidence PR | Contextual PR description. | `github_pr.py` | Embed hash, RED/GREEN output, risk in PR body. | T3.1 | Opened PR contains all 4 evidence blocks. | [ ] |

### P4: Post-Merge Verification
| ID | Title | Objective | Inspect | Requirements | Dependencies | Acceptance | Done |
|---|---|---|---|---|---|---|---|
| T4.1 | Merge Listener | Trigger on PR closed. | `webhooks.py` | Listen for `pull_request` merged events. | P3 | Backend logs reception of PR merge payload. | [ ] |
| T4.2 | Post-Merge Execution | Verify fix on `main`. | `nodes.py` | Checkout merge SHA and run identical test. | T4.1 | Incident state hits RESOLVED. | [ ] |

### P5: Memory & Analytics
| ID | Title | Objective | Inspect | Requirements | Dependencies | Acceptance | Done |
|---|---|---|---|---|---|---|---|
| T5.1 | Seed Migration | Flag demo data. | `seed_db.py`, `models.py` | Set `is_seed=True` on existing rows. | P4 | DB query ignores seeded data. | [ ] |
| T5.2 | Analytics Aggregation | Compute true MTTR. | `roi.py` | Derive stats only from RESOLVED `recovery_runs`. | T5.1 | Dashboard shows 0 if DB has no real runs. | [ ] |

### P6: Polish (Optional)
| ID | Title | Objective | Inspect | Requirements | Dependencies | Acceptance | Done |
|---|---|---|---|---|---|---|---|
| T6.1 | Presentation Mode | A UI recording mode. | `frontend/app/layout.tsx`| Toggle increasing root `rem` size. | P5 | UI enlarges on toggle click. | [ ] |

---

## Dependency Graph
`P0 (Safety) -> P1 (Triggers) -> P2 (Verification) -> P3 (Resolution) -> P4 (Finality) -> P5 (Metrics) -> P6 (Polish)`

## Risk Register
1. **Sandbox Setup Time:** Moving from simple script execution to isolated pre/post state container management may be complex. 
2. **GitHub API Permissions:** Transitioning from OAuth read/write to GitHub App (required for Check Runs).
3. **Flaky Tests:** Native repo tests failing the GREEN check due to timing, halting the pipeline.

## Do Not Touch List
- The underlying `NebiusNemotron` class implementation (Token Factory integration is already functional).
- Frontend color schemes, styling structure, or core React routing.
- The PostgreSQL `Incident` primary key schemas (ensure backwards compatibility).

## Per-Phase Regression Checklist
- [ ] Pipeline compiles and starts `uvicorn` successfully.
- [ ] A manual incident trigger still successfully produces a PR.
- [ ] The Mission Control UI still successfully consumes SSE events.
- [ ] No regression introduced into Token Factory API invocations.

## Timeline
- **Feature Freeze:** Oct 23
- **Video Recording:** Oct 24-26
- **Submission Deadline:** Oct 28
