# What Changed During the Submission Period

This document outlines the major features and improvements built into Antigravity during the official hackathon submission period (Phases 1-9).

## 1. Core State & Data Persistence
- **Phase 1**: Migrated from a mock in-memory store to a robust SQLite database for tracking incident lifecycles (`backend/db/models.py`). 
- **Telemetry**: Upgraded the internal telemetry manager to record real-time node latencies, token consumption, and model routing metrics directly into the database.

## 2. CI/CD Integration & GitHub Webhooks
- **Phase 2 & 5**: Implemented a secure HTTP webhook ingress (`backend/recovery_ext/webhook_ingress.py`) that successfully intercepts GitHub `workflow_run` failure payloads.
- Added end-to-end commit deduplication and infinite loop protection against the bot's own branches.
- Implemented real-time polling in the UI (`frontend/app/page.tsx`) using Server-Sent Events to automatically reflect CI fixes without page reloads.

## 3. UI/UX Polish
- **Phase 3**: Performed a holistic design review. Fixed wrapping on navigation labels, corrected color semantics for risk bars (low risk = green, high risk = red/amber), applied syntax highlighting to markdown patches, and ensured all repository selectors handle long names gracefully.

## 4. Multi-Model Tiering with Nebius & Nemotron
- **Phase 4**: Re-architected the `NebiusNemotron` LLM client (`backend/llm/nebius.py`) to support multi-model routing.
- **Triage**: Handled by the extremely fast `nvidia/Nemotron-3_5-Lightning` model for low-latency initial decisions.
- **Root Cause & Patch Generation**: Routed to the high-capacity `nvidia/Nemotron-3_5-Ultra` or strong standard model for deep logical synthesis.

## 5. Explainable Risk Gateway & Demo Scenarios
- **Phase 6**: Added an independent `critical_paths.py` module to augment file-criticality scoring for specific globs (e.g., `auth/**`).
- Built 3 fully reproducible demo scenarios (`low_risk_calculator`, `medium_risk_data_pipeline`, `high_risk_auth_payments`) bundled in the repository.
- Successfully verified that the Risk Gateway correctly partitions patches into `ALLOW` (<0.3), `APPROVE` (0.3-0.7), and `BLOCK` (>0.7) bands without hardcoded overrides.

## 6. Autonomous Benchmarking
- **Phase 7**: Built an offline benchmark harness (`benchmark/run_benchmark.py`) testing 15 specific python bugs (TypeError, KeyError, Off-by-one, etc.).
- Integrated a live UI panel summarizing the fix-rate, average time-to-remediate, and total tokens consumed across the benchmark.

## 7. Nebius Cloud Deployment & Tavily Research
- **Phase 8**: Augmented the agent's root-cause node to execute an external Web Search via Tavily when `ENABLE_TAVILY_RESEARCH` is enabled.
- Hardened the backend with `RateLimitMiddleware` to protect public endpoints.
- Added Docker Compose configurations (`deploy/docker-compose.demo.yml`) and wrote the `NEBIUS_DEPLOY.md` guide for serverless endpoint deployment.
- Enforced a `PUBLIC_DEMO_MODE` to safely sandbox public demonstration traffic.
