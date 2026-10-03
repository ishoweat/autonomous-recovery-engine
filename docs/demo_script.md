# Demo Video Script (3 Minutes)

## Setup
- **Screen 1**: GitHub Repository (demo scenario).
- **Screen 2**: Antigravity Mission Control UI (Dashboard).
- **Screen 3**: Terminal for running scripts (optional if using fully autonomous hooks).

---

## 0:00 - 0:20 | Introduction & The Problem
*(Camera on speaker, screen showing a failing GitHub Actions run)*
**Speaker**: "Software incidents cost companies millions in downtime and developer burnout. Current CI/CD pipelines tell you *that* something broke, but rely on human engineers to triage, debug, and fix it. We built Antigravity: an Autonomous Reliability Engine powered by Nebius and NVIDIA Nemotron, designed to sit directly in your CI pipeline and fix bugs the second they occur."

## 0:20 - 1:50 | The Autonomous Fix (ALLOW Path)
*(Screen: GitHub repo. Trigger the `low_risk_calculator` scenario by merging a broken PR or pushing a failing commit)*
**Speaker**: "Let's see it in action. A developer just merged a broken commit. Our GitHub Action fails, sending a webhook to Antigravity."
*(Switch to Antigravity Mission Control UI. Show the pipeline steps lighting up in real-time)*
**Speaker**: "Antigravity instantly spins up. It uses a lightning-fast Nemotron model for triage, then hands the stack trace to a stronger Nemotron reasoning model to isolate the root cause. Notice the 'Evidence' links—we use the Tavily API to actively research known issues."
*(Show the 'Sandbox Verify' step passing)*
**Speaker**: "It drafts a patch and spins up an isolated test sandbox. It applies the fix, re-runs the tests, and they pass! Because the Risk Gateway scored this as an 'ALLOW' (low risk), it autonomously pushes the fix back to GitHub as a PR and merges it."
*(Switch back to GitHub repo showing the newly merged fix PR)*

## 1:50 - 2:30 | The Risk Gateway (APPROVE & BLOCK Paths)
*(Screen: Mission Control, clicking into 'Demo Scenarios' panel for the high-risk and medium-risk scenarios)*
**Speaker**: "But we can't blindly trust AI to merge everything. Our deterministic Risk Gateway evaluates four axes: File Criticality, Test Coverage, Patch Size, and Security Surface."
*(Show the Medium Risk 'APPROVE' UI)*
**Speaker**: "For this data pipeline bug, the score hit the 'APPROVE' threshold. The AI prepares the PR, but halts and requires a human click to deploy."
*(Show the High Risk 'BLOCK' UI)*
**Speaker**: "And for this payments module bug—because it touches sensitive `auth/` paths—it hits 'BLOCK'. The system aborts the automated merge entirely and escalates it to a human incident responder with a full RCA report."

## 2:30 - 2:50 | Technology & Benchmarks
*(Screen: Mission Control 'Autonomous Benchmark Results' panel)*
**Speaker**: "Under the hood, we rely entirely on the Nebius Token Factory serving NVIDIA Nemotron models. We built a local benchmark runner that evaluates 15 different regression scenarios across the pipeline. We achieved a high fix rate, averaging under 10 seconds per incident, proving the low latency of the Nebius infrastructure."

## 2:50 - 3:00 | Impact & Future
*(Camera on speaker)*
**Speaker**: "Antigravity transforms CI/CD from a passive alarm system into an active self-healing organism. Thank you to Nebius and NVIDIA!"
