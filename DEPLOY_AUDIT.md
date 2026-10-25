# Production Deployment Audit: Autonomous Recovery Engine (ARE)

**Auditor:** Senior DevOps Engineer  
**Audit Type:** Read-Only Full-Stack Repository Deployment Audit  
**Date:** October 2026  
**Target Environment:** Netlify (Frontend) + Containerized Cloud Host / Nebius (Backend)  
**Security Status:** Read-Only Audit Completed (Zero files modified/deleted outside this audit report; all secret tokens masked)

---

## Executive Summary

The **Autonomous Recovery Engine (ARE)** consists of a **Next.js 14.2 App Router frontend** and a **FastAPI + LangGraph backend** with Docker-isolated test verification sandboxing.

### Key Deployment Findings:
1. **Frontend Netlify Readiness:** The frontend compiles 100% cleanly into static pages (`next build` succeeds with zero errors, producing 8 static routes). However, **it will fail in production** without 3 critical adjustments:
   - Variable name mismatch: `netlify.toml` injects `NEXT_PUBLIC_API_URL`, whereas `next.config.mjs` strictly expects `NEXT_PUBLIC_API_BASE_URL`.
   - Hardcoded localhost redirects in client code (`connect/page.tsx:237` navigates to `http://localhost:8000/auth/github/login`, and `RecoveryCompletePanel.tsx:155` fetches `http://127.0.0.1:8000`).
   - CORS origin enforcement on the backend rejects any requests originating from `*.netlify.app` unless configured in `CORS_ORIGINS`.
2. **Backend Infrastructure Requirements:** The backend is a stateful orchestrator with long-running tasks (LangGraph workflows, approval wait gates up to 15m, webhook workers, merge status pollers) and requires a **persistent container/VM runtime**. It mounts `/var/run/docker.sock` to spin up ephemeral network-isolated test containers (with local subprocess fallback). It **cannot** run on standard 10-second serverless execution limits.
3. **Secret Hygiene:** Git history is **clean** (zero leaked credentials committed in git diffs). However, `.gitignore` has an active gap permitting 16 SQLite WAL and SHM database cache files (~150MB) to remain untracked in the working tree, at risk of accidental commitment.
4. **OAuth Loophole:** The backend OAuth callback handler (`backend/api/auth.py:173, 184`) hardcodes redirects to `http://localhost:8000` and `http://localhost:3000`. On a public domain, authentication dumps the user onto localhost instead of the deployed frontend.

---

## 1. STACK

| Component | Attribute | Value / Specification | Reference |
| :--- | :--- | :--- | :--- |
| **Frontend** | Framework | Next.js 14.2.21 (React 18.3.1, TypeScript 5.7.2) | `frontend/package.json:15-17` |
| | Routing Architecture | App Router (`frontend/app/`), 100% Client-Side Static Routes | Verified via `next build` |
| | Build Command | `npm run build` (runs `next build`) | `frontend/package.json:7` |
| | Output Directory | `.next` (Standalone mode configured: `output: "standalone"`) | `frontend/next.config.mjs:4`, `netlify.toml:4` |
| | Target Node Version | Node.js 20 LTS (`node:20-alpine`) | `frontend/Dockerfile:3, 11, 23` |
| | Active Toolchain | Node v24.19.0, npm 11.x (No `.nvmrc` / `.node-version`) | System detection |
| **Backend** | Framework | FastAPI 0.115.x + Starlette + Pydantic v2 + Pydantic-Settings | `requirements.txt:1, 6-7` |
| | Entrypoint | `backend.main:app` (via Uvicorn) | `backend/Dockerfile:35`, `backend/main.py:312` |
| | ASGI Webserver | `uvicorn[standard]>=0.34,<1.0` | `requirements.txt:2` |
| | Python Version | Python 3.11 (`FROM python:3.11-slim`) | `backend/Dockerfile:3` |
| | Requirements File | `requirements.txt` (Root directory, 21 pinned packages) | `requirements.txt:1-21` |
| | Orchestrator | LangGraph 1.0.x with AsyncPostgresSaver / MemorySaver | `requirements.txt:10-11`, `backend/orchestration/runtime.py` |
| **Docker** | Backend Image | `backend/Dockerfile` (Multi-stage Debian-slim with git, non-root `appuser`) | `backend/Dockerfile:1-37` |
| | Frontend Image | `frontend/Dockerfile` (Multi-stage Node alpine with standalone server) | `frontend/Dockerfile:1-43` |
| | Production Compose | `docker-compose.prod.yml` (Postgres 16, backend, frontend, host docker.sock) | `docker-compose.prod.yml:1-110` |
| | Demo Compose | `deploy/docker-compose.demo.yml` | `deploy/docker-compose.demo.yml:1-31` |

---

## 2. LOCALHOST REFS

Every hardcoded `localhost`, `127.0.0.1`, and explicit port reference (`:8000`, `:3000`, `:5432`, `:6379`) across the entire repository:

| File Location | Line | Category | Exact Snippet / Context | Impact on Remote Production |
| :--- | :--- | :--- | :--- | :--- |
| `frontend/app/connect/page.tsx` | 237 | **Client OAuth Trigger** | `onClick={() => window.location.href = "http://localhost:8000/auth/github/login"}` | **CRITICAL BREAK:** Clicking "Connect with GitHub" navigates user to `http://localhost:8000` instead of deployed backend |
| `frontend/components/RecoveryCompletePanel.tsx` | 155 | **Client Webhook Call** | `fetch("http://127.0.0.1:8000/api/v1/webhooks/github", ...)` | **CRITICAL BREAK:** Triggering ingress simulation sends fetch to user's local machine |
| `frontend/lib/api.ts` | 9 | **Client API Fallback** | `process.env.NEXT_PUBLIC_API_BASE_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"` | Defaults all client API calls to localhost:8000 if env vars are unset at build |
| `frontend/next.config.mjs` | 9 | **Next.js Rewrite Fallback** | `const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL \|\| "http://127.0.0.1:8000";` | Next.js rewrites fallback to 127.0.0.1:8000 (note: ignores `NEXT_PUBLIC_API_URL`) |
| `frontend/.env.local.example` | 1 | **Frontend Env Example** | `NEXT_PUBLIC_API_URL=http://localhost:8000` | Sample config for local dev |
| `backend/api/auth.py` | 173 | **OAuth Callback (Step 1)** | `redirect_url = f"http://localhost:8000/auth/github/set-cookie?session_id={session_id}"` | **CRITICAL BREAK:** Backend redirects browser to `http://localhost:8000` after OAuth exchange |
| `backend/api/auth.py` | 184 | **OAuth Callback (Step 2)** | `frontend_url = f"http://localhost:3000/detect?session_id={session_id}"` | **CRITICAL BREAK:** Backend redirects browser to `http://localhost:3000` instead of Netlify |
| `backend/main.py` | 130 | **CORS Hardcoded Ingress** | `for local_dev_url in ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"]:` | Injects local dev URLs into allowed CORS list |
| `backend/main.py` | 136 | **CORS Allowed Regex** | `allow_origin_regex=r"^https?://(localhost\|127\.0\.0\.1)(:\d+)?$"` | Permissive CORS regex matches only localhost/127.0.0.1 |
| `backend/config/settings.py` | 24 | **Database URL Default** | `default="postgresql+asyncpg://postgres:postgres@localhost:5432/recovery_engine"` | Default database connection string |
| `backend/config/settings.py` | 49 | **OAuth Redirect Default** | `default="http://127.0.0.1:8000/api/auth/github/callback"` | Default redirect URI sent to GitHub during OAuth flow |
| `backend/services/session_service.py` | 71 | **Redis URL Default** | `self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")` | Falls back to local Redis port 6379 (falls back to memory if down) |
| `docker-compose.prod.yml` | 39 | **Database Connection** | `DATABASE_URL: postgresql+asyncpg://${POSTGRES_USER:-recovery}:${POSTGRES_PASSWORD}@postgres:5432/...` | Internal Docker network DB port |
| `docker-compose.prod.yml` | 48 | **CORS Default** | `CORS_ORIGINS: ${CORS_ORIGINS:-http://localhost:3000}` | Default compose CORS configuration |
| `docker-compose.prod.yml` | 53 | **Backend Host Port** | `"${BACKEND_PORT:-8000}:8000"` | Docker container port binding |
| `docker-compose.prod.yml` | 60 | **Backend Healthcheck** | `"import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"` | Container healthcheck query |
| `docker-compose.prod.yml` | 75, 83 | **Frontend Build Arg & Env** | `NEXT_PUBLIC_API_BASE_URL: ${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8000}` | Build-time and runtime env injection |
| `docker-compose.prod.yml` | 85 | **Frontend Host Port** | `"${FRONTEND_PORT:-3000}:3000"` | Docker container port binding |
| `docker-compose.prod.yml` | 92 | **Frontend Healthcheck** | `"fetch('http://localhost:3000').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"` | Container healthcheck query |
| `deploy/docker-compose.demo.yml` | 9, 18, 28, 30 | **Demo Compose Ports** | `8000:8000`, `CORS_ORIGINS=http://localhost:3000`, `3000:3000`, `NEXT_PUBLIC_API_URL=...:8000` | Demo container orchestration |
| `scripts/send_test_webhook.py` | 10 | **Test Script Destination** | `url = "http://localhost:8000/webhook/github"` | Local CLI webhook forwarding script |
| `scripts/setup_github_oauth.sh` | 12 | **Setup Instruction** | `echo "5. Authorization callback URL: http://localhost:3000/api/auth/callback/github ..."` | **MISLEADING DOC:** Mentions port 3000 instead of backend port 8000 |
| `scripts/start_tunnel.sh` | 23, 43, 46, 60, 64, 79, 85 | **Tunnel Forwarding** | `http://127.0.0.1:${BACKEND_PORT}...` | Local tunnel targets for Smee / Cloudflare / Ngrok |
| `scripts/demo_high_risk.py` | 8, 12, 81 | **Demo Script CLI** | `parser.add_argument("--url", default="http://localhost:8000")` | CLI script default endpoint |
| `.env.example` | 30, 32, 33, 62-64 | **Config Examples** | `GITHUB_REDIRECT_URI=http://127.0.0.1:8000/...`, `CORS_ORIGINS=http://localhost:3000`, etc. | Template environment variables |
| `.env` | 24, 25, 32 | **Active Config** | `CORS_ORIGINS=http://localhost:3000`, `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`, `GITHUB_REDIRECT_URI=...` | Active developer environment values |

---

## 3. API CALLS

### Architecture & Invocation Method
- **Client-Side `fetch` Calls:** 100% of all data transfers between frontend and backend are executed via standard browser `window.fetch()` inside client components (`"use client"`).
- **No Axios:** Axios is neither installed nor referenced.
- **Direct Cross-Origin CORS Model:**
  All frontend API helper functions in `frontend/lib/api.ts` construct absolute URLs:
  ```ts
  export const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000";
  ```
  Every request (e.g., `fetch(`${API_BASE_URL}/api/remediate`)`) targets the backend directly across origins, accompanied by `credentials: "include"` and `X-Session-ID` / `Authorization: Bearer` headers.
- **Next.js Rewrites Analysis (`frontend/next.config.mjs`):**
  Next.js defines a rewrite:
  ```js
  async rewrites() {
    const backendUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  }
  ```
  **Critical Finding:** Because client code in `frontend/lib/api.ts` prepends `${API_BASE_URL}` to all calls, browser requests bypass the Next.js rewrite engine completely. Furthermore, authentication endpoints (`/auth/github/*`) and webhook endpoints (`/webhook/github`) do not use the `/api/` prefix, so they would never match the rewrite rule regardless.
- **Server Actions & Route Handlers:**
  - Next.js Route Handlers (`app/api/**/route.ts`): **Zero exist**.
  - Next.js Server Actions (`"use server"`): **Zero exist**.
  - Server Runtime Dependency: **None**. The frontend is an entirely static Single-Page Application (SPA) compiled by Next.js.
- **Real-Time Streaming:**
  Incident telemetry streaming is consumed in `frontend/app/detect/page.tsx:704` via standard browser `EventSource` (`new EventSource(incidentStreamUrl(incidentId))`), connecting to the backend SSE endpoint `GET /api/v1/incident/{incident_id}/stream`.

---

## 4. ENV VARS

Complete inventory of every environment variable accessed in the codebase:

| Variable Name | Reading File & Line | Secret vs Public | Default / Hardcoded Fallback | Currently Set In | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `NEXT_PUBLIC_API_BASE_URL` | `frontend/next.config.mjs:9`, `frontend/lib/api.ts:7`, `docker-compose.prod.yml:75` | **Public** | `http://127.0.0.1:8000` / `http://localhost:8000` | `.env`, `.env.example`, `docker-compose.prod.yml` | Backend API URL for frontend build & client fetch |
| `NEXT_PUBLIC_API_URL` | `frontend/lib/api.ts:8`, `netlify.toml:11`, `deploy/docker-compose.demo.yml:30` | **Public** | Unset | `netlify.toml`, `.env.local.example` | Secondary fallback for API URL |
| `NEXT_PRIVATE_LOCAL_WEBPACK` | `netlify.toml:10` | **Public** | Unset | `netlify.toml` | Build flag for Netlify Next plugin |
| `DATABASE_URL` | `backend/config/settings.py:23`, `docker-compose.prod.yml:39` | **Secret** | `postgresql+asyncpg://postgres:postgres@localhost:5432/recovery_engine` | `.env`, `.env.example`, `docker-compose.prod.yml` | Async database connection string (PostgreSQL or SQLite) |
| `DATABASE_PATH` | `backend/recovery_ext/fork_pr.py:186` | **Public/Internal** | `./recovery.db` | Unset (falls back to `./recovery.db`) | Local SQLite path used specifically by `fork_pr.py` |
| `POSTGRES_DB` | `docker-compose.prod.yml:11` | **Public/Internal** | `recovery_engine` | `.env`, `docker-compose.prod.yml` | PostgreSQL database name |
| `POSTGRES_USER` | `docker-compose.prod.yml:12` | **Public/Internal** | `recovery` | `.env`, `docker-compose.prod.yml` | PostgreSQL username |
| `POSTGRES_PASSWORD` | `docker-compose.prod.yml:13` | **Secret** | Required (`?POSTGRES_PASSWORD must be set`) | `.env` [MASKED] | PostgreSQL password |
| `NEBIUS_API_KEY` | `backend/config/settings.py:85`, `docker-compose.prod.yml:41` | **Secret** | `""` | `.env` [MASKED], `docker-compose.prod.yml` | Nebius Token Factory API key |
| `NEBIUS_BASE_URL` | `backend/config/settings.py:90`, `docker-compose.prod.yml:42` | **Public** | `https://api.tokenfactory.nebius.com/v1/` | `.env`, `.env.example`, `docker-compose.prod.yml` | Nebius OpenAI-compatible base URL |
| `NEBIUS_MODEL` | `backend/config/settings.py:95`, `docker-compose.prod.yml:43` | **Public** | `nvidia/Nemotron-3_5-Lightning` | `.env`, `.env.example`, `docker-compose.prod.yml` | Primary LLM model identifier |
| `NEMOTRON_MODEL` | `backend/config/settings.py:100` | **Public** | `None` (falls back to `NEBIUS_MODEL`) | `.env.example` | Optional alias for primary model |
| `NEBIUS_FAST_MODEL` | `backend/config/settings.py:105` | **Public** | `None` (falls back to `NEBIUS_MODEL`) | `.env.example` | Optional fast model for triaging |
| `NEBIUS_STRONG_MODEL` | `backend/config/settings.py:110` | **Public** | `None` (falls back to `NEBIUS_MODEL`) | `.env.example` | Optional strong model for complex fixes |
| `NEBIUS_TEMPERATURE` | `backend/config/settings.py:137` | **Public** | `0.1` | `.env.example` | Model sampling temperature |
| `NEBIUS_MAX_TOKENS` | `backend/config/settings.py:142` | **Public** | `8192` | `.env`, `.env.example` | Model token generation cap |
| `NEBIUS_TIMEOUT_SECONDS` | `backend/config/settings.py:147` | **Public** | `90.0` | `.env.example` | LLM HTTP client request timeout |
| `PRICE_PER_MTOK_FAST` | `backend/config/settings.py:127` | **Public** | `None` | `.env.example` | Telemetry pricing calculation |
| `PRICE_PER_MTOK_STRONG` | `backend/config/settings.py:132` | **Public** | `None` | `.env.example` | Telemetry pricing calculation |
| `GITHUB_TOKEN` | `backend/config/settings.py:33`, `backend/orchestration/nodes.py:1758`, `backend/api/github_workspace.py:291`, etc. | **Secret** | `""` | `.env` [MASKED], `docker-compose.prod.yml` | System GitHub PAT for repository cloning, tree reading, and PR creation |
| `GITHUB_WEBHOOK_SECRET` | `backend/config/settings.py:28`, `docker-compose.prod.yml:46` | **Secret** | `""` | `.env` [MASKED], `docker-compose.prod.yml` | HMAC-SHA256 signature secret for inbound webhooks |
| `GITHUB_CLIENT_ID` | `backend/config/settings.py:38` | **Public** | `""` | `.env` [MASKED], `.env.example` | GitHub OAuth App Client ID |
| `GITHUB_CLIENT_SECRET` | `backend/config/settings.py:43` | **Secret** | `""` | `.env` [MASKED], `.env.example` | GitHub OAuth App Client Secret |
| `GITHUB_REDIRECT_URI` | `backend/config/settings.py:48` | **Public** | `http://127.0.0.1:8000/api/auth/github/callback` | `.env`, `.env.example` | Callback URI registered in GitHub OAuth app |
| `GITHUB_APP_NAME` | `backend/api/github_workspace.py:836` | **Public** | `Autonomous Recovery Engine` | Unset (falls back to default) | Name used in PR commits |
| `CORS_ORIGINS` | `backend/main.py:129`, `docker-compose.prod.yml:48` | **Public** | `*` (falls back to localhost URLs) | `.env`, `.env.example`, `docker-compose.prod.yml` | Comma-separated allowed CORS origins |
| `FRONTEND_URL` | `deploy/docker-compose.demo.yml:18`, `.env.example:63` | **Public** | `http://localhost:3000` | `.env.example`, `deploy/docker-compose.demo.yml` | Frontend base URL for redirects |
| `BACKEND_URL` | `deploy/docker-compose.demo.yml:30`, `.env.example:64` | **Public** | `http://localhost:8000` | `.env.example`, `deploy/docker-compose.demo.yml` | Backend base URL |
| `ENVIRONMENT` / `APP_ENV` | `backend/config/settings.py:21`, `docker-compose.prod.yml:38`, `backend/orchestration/risk.py:237` | **Public** | `development` | `.env`, `.env.example`, `docker-compose.prod.yml` | Runtime environment toggle (`production` vs `development`) |
| `LOG_LEVEL` | `docker-compose.prod.yml:49` | **Public** | `INFO` | `.env`, `.env.example`, `docker-compose.prod.yml` | Logging verbosity |
| `ALLOW_MOCK_MODE` | `backend/config/settings.py:54` | **Public** | `False` | `.env.example`, `deploy/docker-compose.demo.yml` | Enables mock responses when credentials are unconfigured |
| `ENABLE_LLM_CACHE` | `backend/config/settings.py:59` | **Public** | `False` | `.env.example` | In-memory semantic/hash cache for LLM responses |
| `SHADOW_MODE` | `backend/config/settings.py:64` | **Public** | `True` | `.env.example` | Shadow analysis mode without mutating production PRs |
| `WEBHOOK_MAX_BODY_BYTES` | `backend/config/settings.py:69` | **Public** | `2000000` (2 MB) | `.env.example` | Webhook request payload size ceiling |
| `SSE_HEARTBEAT_SECONDS` | `backend/config/settings.py:74` | **Public** | `15.0` | `.env.example` | Telemetry SSE ping interval |
| `SSE_QUEUE_SIZE` | `backend/config/settings.py:79` | **Public** | `100` | `.env.example` | Per-client buffer queue for SSE events |
| `LANGGRAPH_CHECKPOINT_SETUP` | `backend/config/settings.py:153` | **Public** | `True` | Unset (uses default) | Automatically executes `AsyncPostgresSaver.setup()` |
| `TAVILY_API_KEY` | `backend/services/tavily_evidence.py:147`, `backend/orchestration/nodes.py:239` | **Secret** | `""` | `.env` [MASKED], `docker-compose.prod.yml` | Tavily Search API key for live error/library research |
| `ENABLE_TAVILY_RESEARCH` | `backend/recovery_ext/flags.py:55` | **Public** | `False` | `deploy/docker-compose.demo.yml` | Feature flag to activate live Tavily web research |
| `FORCE_TAVILY_TIMEOUT` | `backend/services/tavily_evidence.py:177` | **Public/Debug** | `False` | Unset (test script only) | Simulates search latency timeout |
| `REDIS_URL` | `backend/services/session_service.py:71` | **Secret** | `redis://localhost:6379/0` | Unset (uses memory dictionary if absent) | Distributed user session cache |
| `SESSION_TTL_SECONDS` | `backend/services/session_service.py:72` | **Public** | `3600` (1 hour) | Unset (uses default) | User session expiry time |
| `ENABLE_PERSISTENCE` | `backend/recovery_ext/flags.py:19` | **Public** | `False` | `.env.example` | Enables LangGraph Postgres persistence |
| `ENABLE_WEBHOOK_INGRESS` | `backend/recovery_ext/flags.py:23` | **Public** | `False` | `.env.example` | Enables background webhook queue worker |
| `ENABLE_APPROVAL_GATE` | `backend/recovery_ext/flags.py:27` | **Public** | `False` | `.env.example` | Halts execution on high-risk fixes for human approval |
| `APPROVAL_TIMEOUT_SECONDS` | `backend/recovery_ext/approval_gate.py:81` | **Public** | `900` (15 minutes) | Unset (uses default) | Max wait time before auto-rejecting approval |
| `ENABLE_BLOCK_ESCALATION` | `backend/recovery_ext/flags.py:31` | **Public** | `False` | `.env.example` | Blocks high-risk patches and notifies security |
| `ENABLE_SANDBOX_HARDENING` | `backend/recovery_ext/flags.py:35` | **Public** | `False` | `.env.example` | Enables seccomp, drop-caps, and no-new-privileges |
| `RECOVERY_SANDBOX_MEMORY_LIMIT` | `backend/recovery_ext/sandbox_policy.py:52` | **Public** | `512m` | Unset (uses default) | Docker container RAM ceiling |
| `RECOVERY_SANDBOX_CPU_LIMIT` | `backend/recovery_ext/sandbox_policy.py:53` | **Public** | `1.0` | Unset (uses default) | Docker container CPU quota |
| `RECOVERY_SANDBOX_PIDS_LIMIT` | `backend/recovery_ext/sandbox_policy.py:54` | **Public** | `128` | Unset (uses default) | Docker container process limit |
| `RECOVERY_SANDBOX_TIMEOUT_SECONDS` | `backend/recovery_ext/sandbox_policy.py:55` | **Public** | `120` | Unset (uses default) | Sandbox execution timeout ceiling |
| `ENABLE_AUTO_MERGE` | `backend/recovery_ext/flags.py:39` | **Public** | `False` | `.env`, `.env.example` | Auto-merges PR upon verified test pass |
| `MERGE_POLL_INTERVAL_SECONDS` | `backend/recovery_ext/merge_poller.py:18` | **Public** | `10` | Unset (uses default) | Polling frequency for PR status checks |
| `ENABLE_POST_MERGE_VERIFY` | `backend/recovery_ext/flags.py:43` | **Public** | `False` | `.env.example` | Triggers follow-up verification run post-merge |
| `POST_MERGE_FORCE_EXIT_CODE` | `backend/recovery_ext/post_merge.py:113` | **Public/Debug** | `None` | Unset | Injects test exit code for test verification |
| `POST_MERGE_BLOCK_FINISHING` | `backend/recovery_ext/post_merge.py:114` | **Public/Debug** | `False` | Unset | Blocks completion for pipeline stress-testing |
| `ENABLE_DEMO_SCENARIOS` | `backend/recovery_ext/flags.py:47` | **Public** | `False` | `.env.example` | Loads synthetic demo incidents |
| `ENABLE_BENCHMARK_VIEW` | `backend/recovery_ext/flags.py:51` | **Public** | `False` | `.env.example` | Displays benchmark comparison tab |
| `ENABLE_RATE_LIMITING` | `backend/recovery_ext/flags.py:59` | **Public** | `False` | `deploy/docker-compose.demo.yml` | Activates rate limit middleware |
| `PUBLIC_DEMO_MODE` | `backend/recovery_ext/flags.py:63` | **Public** | `False` | `deploy/docker-compose.demo.yml` | Disables state mutation for public showcases |
| `ENABLE_FORK_AND_PR` | `backend/recovery_ext/flags.py:67` | **Public** | `False` | `.env.example` | Permits forking external repositories |
| `PUBLIC_DEMO_ALLOWLIST` | `backend/recovery_ext/fork_pr.py:241` | **Public** | `octocat/Hello-World,Sahil707-pop/autonomous-recovery-engine` | Unset (uses default) | Allowed repos for public demo mode |
| `ENABLE_REAL_METRICS` | `backend/api/roi.py:55`, `backend/api/learning.py:52` | **Public** | `false` | Unset (uses default) | Toggles real database metrics vs synthetic baseline |
| `ENGINEER_HOURLY_RATE` / `ASSUMED_ENGINEER_HOURLY_USD` | `backend/services/roi.py:29`, `backend/recovery_ext/metrics_service.py:19` | **Public** | `85.0` | Unset (uses default) | Hourly rate assumption for ROI calculations |
| `ASSUMED_MANUAL_FIX_HOURS` | `backend/recovery_ext/metrics_service.py:20` | **Public** | `1.5` | Unset (uses default) | Duration assumption for ROI calculations |
| `CRITICAL_PATHS_JSON` | `backend/recovery_ext/critical_paths.py:12` | **Public** | `None` | Unset | Custom path weights for risk scoring engine |
| `FORCE_RISK_SCORE` | `backend/orchestration/risk.py:235` | **Public/Debug** | `None` | Unset | Overrides risk engine output (non-production only) |
| `SCAVENGER_ORPHAN_AGE_SECONDS` | `backend/recovery_ext/scavenger.py:39` | **Public** | `600` (10 minutes) | Unset | Max age before cleaning abandoned containers |

---

## 5. SECRET LEAKS & GIT AUDIT

### 1. Hardcoded Credentials Scan (Workspace Files)
A comprehensive regex analysis for PATs (`ghp_`, `github_pat_`), API tokens (`tvly-`, `sk-`), Bearer tokens, and credential assignments identified **zero production secret leaks** in source code. All matched items are test strings, mock data, or documentation examples:

| File Location | Line | Type | Classification | Detail |
| :--- | :--- | :--- | :--- | :--- |
| `tests/test_universal_ai_repair_engine.py` | 223–224 | Secret Pattern | **Safe Mock** | Planted fake token string used to verify that the AST security gate blocks hardcoded secrets |
| `tests/test_universal_repair.py` | 126 | Secret Pattern | **Safe Mock** | Planted fake token string verifying AST security checks |
| `tests/test_real_github_pr_verification.py` | 208 | `ghp_...` | **Safe Mock** | Mock token named `ghp_real_verification_test_pipeline` passed to mock state |
| `docs/spec/MEMORY.md` | 40 | `ghp_...` | **Documentation** | Spec markdown illustrating regex redaction behavior |
| `scripts/quick_eval_5.py` | 96, 141 | `tvly-...` | **Safe Mock** | Dummy string `"tvly-live-research-active"` set in `os.environ` during test suite |
| `scripts/verify_failure_paths.py` | 38 | `tvly-...` | **Safe Mock** | Dummy string `"tvly-live-research-active"` set in `os.environ` during test suite |
| `scratch_test_phase4_github_fork.py` | 12 | Token | **Safe Mock** | Dummy argument `token="fake-token"` |

### 2. Committed `.env` Files
- `.env`: **NOT committed** (Confirmed via `git log --all --full-history -- ".env"`).
- `.env.example`: Committed in git (Contains only sanitized placeholders: `your_nebius_api_key`, `your_github_token`, etc.).
- `frontend/.env.local.example`: Committed in git (Contains only `NEXT_PUBLIC_API_URL=http://localhost:8000`).

### 3. Git History Analysis
A full forensic scan across all historical commits and git diffs (`git log -p --all`) using regex patterns for GitHub tokens, Tavily keys, and OpenAI keys yielded **0 leaked secrets in git history**.

### 4. `.gitignore` Gaps
**Major Gap:** SQLite Auxiliary Database Files & Engine Run Dumps.
`.gitignore` currently contains:
```gitignore
recovery.db
backend/sandbox/tmp/
*.log
```
However, it fails to wildcard-match SQLite write-ahead log (`-wal`) and shared-memory (`-shm`) files, as well as files containing spaces.
**Result:** The following **16 uncommitted database files (~150MB total)** are currently untracked in the working directory:
- `recovery 2.db-shm`, `recovery 2.db-wal` (296 KB)
- `recovery 3.db-shm`, `recovery 3.db-wal` (4.3 MB)
- `recovery 4.db-shm`, `recovery 4.db-wal` (4.3 MB)
- `recovery 5.db-shm`, `recovery 5.db-wal` (762 KB)
- `recovery 6.db-shm`, `recovery 6.db-wal`
- `recovery 7.db-shm`, `recovery 7.db-wal` (82 KB)
- `recovery 8.db-shm`, `recovery 9.db-shm`, `recovery 10.db-shm`, `recovery 11.db-shm`
- `.recovery/` directory
- Untracked root scratch scripts: `page_fixes.py`, `patch_nebius.py`, `test_nebius.py`, `update_nodes.py`, `update_telemetry.py`.

Any accidental `git add .` or `git add -A` will commit 150MB of local SQLite binary WAL logs into git.

---

## 6. CORS (Cross-Origin Resource Sharing)

### Current Implementation (`backend/main.py:128–140`):
```python
import os
cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "*").split(",") if o.strip()]
for local_dev_url in ["http://localhost:3000", "http://localhost:3001", "http://127.0.0.1:3000", "http://127.0.0.1:3001"]:
    if local_dev_url not in cors_origins:
        cors_origins.append(local_dev_url)
application.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Analysis & Production Vulnerabilities:
1. **Allowed Origins List:** In `.env`, `CORS_ORIGINS=http://localhost:3000`. In `docker-compose.prod.yml`, it defaults to `http://localhost:3000`.
2. **Regex Whitelist:** The regex `r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"` only matches loopback addresses.
3. **Credentials Restriction:** `allow_credentials=True` is enabled.
   - Under standard CORS specifications (W3C / WHATWG), when `credentials: "include"` is set on client fetch calls, browsers **strictly forbid wildcard `*`** in `Access-Control-Allow-Origin`.
   - Therefore, requests from a Netlify domain (e.g. `https://autonomous-recovery.netlify.app`) will be **rejected by the browser** with a preflight CORS violation unless `https://autonomous-recovery.netlify.app` is explicitly appended to `CORS_ORIGINS`.

---

## 7. OAUTH & WEBHOOKS

### 1. GitHub OAuth Flow
The OAuth flow is split between frontend and backend:
1. User clicks login in `frontend/app/connect/page.tsx:237`:
   - Code: `window.location.href = "http://localhost:8000/auth/github/login"`
2. Backend generates authorize redirect in `backend/api/auth.py:102`:
   - `https://github.com/login/oauth/authorize?client_id={settings.github_client_id}&scope=repo%20user&redirect_uri={settings.github_redirect_uri}`
3. User authorizes on GitHub; GitHub redirects browser to `GITHUB_REDIRECT_URI`.
4. Backend handles callback in `backend/api/auth.py:121`:
   - Exchanges `code` with GitHub for an `access_token`.
   - Fetches user profile from `https://api.github.com/user`.
   - Creates a server-side session in Redis (or in-memory cache) with ID `sess_<uuid>`.
   - **Hardcoded Redirect 1 (`auth.py:173`):** Redirects to `http://localhost:8000/auth/github/set-cookie?session_id={session_id}`.
5. Cookie Setter handles redirect in `backend/api/auth.py:177`:
   - Sets HTTP-only cookies `session_id` and `github_token`.
   - **Hardcoded Redirect 2 (`auth.py:184`):** Redirects to `http://localhost:3000/detect?session_id={session_id}`.
6. Frontend receives redirect, extracts `session_id` from URL query parameter, saves to `localStorage`, cleans the URL bar, and attaches `X-Session-ID` to all future API calls (`frontend/hooks/useGitHubSession.ts:36-53`).

#### Critical Flaws for Public Domain Deployment:
- **Misleading Documentation:** `scripts/setup_github_oauth.sh:12` tells developers to set the OAuth Callback URL to `http://localhost:3000/api/auth/callback/github`. This endpoint **does not exist** on the frontend. If set, GitHub redirects to Next.js, producing a 404 error.
- **Callback Must Point to Backend:** The true handler is `backend.api.auth:github_callback`, reachable at `https://<backend-domain>/auth/github/callback` (or `/api/v1/auth/callback`).
- **Hardcoded Localhost in Redirects:** `auth.py:173` and `auth.py:184` completely bypass `FRONTEND_URL` and force the browser back to `localhost:8000` and `localhost:3000`.
- **Third-Party Cookie Degradation:** `auth.py:192` sets `samesite="lax"`. If the frontend is on Netlify (`https://*.netlify.app`) and backend is on a separate domain (e.g., `https://api.domain.com`), the cookie will not be sent on cross-site fetch calls. Fortunately, the application's fallback mechanism (`localStorage` + `X-Session-ID: sess_...` header) succeeds if the URL query parameter redirect reaches the frontend.

### 2. GitHub Webhooks Flow
- **Ingress Endpoints:** `POST /webhook/github` and `POST /api/v1/webhooks/github` (`backend/api/webhooks.py:44, 48`).
- **Signature Verification:** Validates `X-Hub-Signature-256` HMAC-SHA256 signature against `GITHUB_WEBHOOK_SECRET` (`verify_github_signature`).
- **Event Handling:** Ingests `workflow_run` failure payloads to trigger autonomous incident creation.
- **Frontend Simulation Call:** `frontend/components/RecoveryCompletePanel.tsx:155` provides a button to simulate real webhook ingress, but hardcodes `http://127.0.0.1:8000/api/v1/webhooks/github`.

### Required Public Domain Configuration:
| Setting | Current Value | Required Production Value |
| :--- | :--- | :--- |
| **GitHub OAuth App: Homepage URL** | `http://localhost:3000` | `https://<your-app>.netlify.app` |
| **GitHub OAuth App: Callback URL** | `http://localhost:3000/api/auth/...` (Docs) / `http://127.0.0.1:8000/...` (.env) | `https://<backend-domain>/auth/github/callback` |
| **Backend `GITHUB_REDIRECT_URI`** | `http://127.0.0.1:8000/auth/github/callback` | `https://<backend-domain>/auth/github/callback` |
| **Backend `FRONTEND_URL`** | `http://localhost:3000` | `https://<your-app>.netlify.app` |
| **GitHub Repo Webhook: Payload URL** | `http://127.0.0.1:8000/webhook/github` (tunnel) | `https://<backend-domain>/webhook/github` |
| **GitHub Repo Webhook: Secret** | Local secret | Matches `GITHUB_WEBHOOK_SECRET` |

---

## 8. BACKEND NEEDS & INFRASTRUCTURE

| Dimension | Repo Capability & Current Mechanism | Production Constraint / Recommendation |
| :--- | :--- | :--- |
| **Docker / Sandbox** | `LocalDockerRunner` (`backend/sandbox/sandbox.py:33`) connects to Docker via `docker.from_env()`. In `docker-compose.prod.yml:51`, mounts `/var/run/docker.sock:/var/run/docker.sock` to execute ephemeral `python:3.11-slim` test containers with network isolation, memory limits (`512m`), and CPU throttling (`1.0`). Has local subprocess fallback (`_run_tests_local`) if Docker ping fails. | Standard serverless platforms (Nebius Serverless Endpoint, AWS Lambda, Cloud Run) cannot mount Docker sockets. For Docker-isolated sandboxing, host backend on a VM (AWS EC2, Hetzner, DigitalOcean, Fly.io machine) or offload test execution to Nebius Serverless Jobs as documented in `deploy/NEBIUS_DEPLOY.md`. |
| **Filesystem Writes** | Writes temporary test workspaces via `tempfile.mkdtemp(prefix="antigravity_sbx_")`, writes `patch.diff` files, performs git clones in `github_workspace.py`, and writes SQLite database files (`recovery.db`). | Host container must allow writes to `/tmp` and persistent storage for `recovery.db` (if PostgreSQL is not used). |
| **Long-Running Tasks** | 1. `lifespan` launches `start_webhook_worker` and `start_merge_poller` (polls GitHub every 10s).<br>2. LangGraph recovery graph execution takes 30s to 180s (multiple LLM calls + test execution in Docker).<br>3. Approval gate (`backend/recovery_ext/approval_gate.py:81`) can wait up to 15 minutes (`APPROVAL_TIMEOUT_SECONDS=900`) for human signoff. | Requires a persistent backend process with HTTP request timeout $\ge 300\text{s}$ (or asynchronous job queues). Serverless functions with 10s/30s timeouts are **incompatible**. |
| **Database** | Dual support: PostgreSQL (`postgresql+asyncpg://...`) and SQLite (`sqlite+aiosqlite:///...`). LangGraph checkpointer uses `AsyncPostgresSaver` when Postgres is active; falls back to in-memory `MemorySaver` when SQLite is used.<br>**Flaw:** `backend/recovery_ext/fork_pr.py:186` hardcodes a direct SQLite connection to `os.getenv("DATABASE_PATH", "./recovery.db")` for consent records. | Production should deploy PostgreSQL 16 (e.g. AWS RDS, Supabase, Neon, or containerized postgres). If Postgres is used, `DATABASE_PATH` must still be writable for `fork_pr.py` unless refactored. |
| **Redis Cache** | `backend/services/session_service.py` connects to Redis (`REDIS_URL`). If Redis is unavailable, it gracefully falls back to an in-memory dictionary. | Optional for single-instance backend; required for multi-instance horizontal scaling. |
| **WebSockets / SSE** | Uses **Server-Sent Events (SSE)** exclusively at `/api/v1/incident/{id}/stream` via `EventSourceResponse`. SSE heartbeats every 15s (`SSE_HEARTBEAT_SECONDS`). WebSockets are not used. | Reverse proxies (Nginx, Cloudflare, Traefik, Caddy) must disable response buffering (`proxy_buffering off;`, `X-Accel-Buffering: no`). |
| **Memory & CPU** | In-memory LangGraph state machine, AST security parsing, LLM streaming, and concurrent test containers. | Minimum: **2 vCPU, 2 GB RAM**. Recommended: **2–4 vCPU, 4–8 GB RAM** if hosting Docker sandbox containers on the same host. |

---

## 9. NETLIFY FIT: FRONTEND EVALUATION

### Will the frontend build on Netlify as-is?
**Build Result:** **YES, the Next.js build succeeds.**  
Running `npm run build` compiles 100% of the routes into static HTML and client-side JavaScript (`○ (Static) prerendered as static content`).

### Deployment Blockers & Breakages:

```
[Netlify User]
      │
      ▼
1. Loads Netlify Frontend (Build succeeds, but bundles baked with NEXT_PUBLIC_API_BASE_URL)
      │
      ├─► 2. Click "Connect with GitHub" ──► navigates to http://localhost:8000/auth/github/login (FAIL)
      │
      ├─► 3. API Calls (fetch) ──► Blocked by Backend CORS (Origin *.netlify.app not allowed) (FAIL)
      │
      ├─► 4. OAuth Callback ──► Backend redirects to http://localhost:3000/detect?session_id=... (FAIL)
      │
      └─► 5. Simulate Webhook ──► fetch("http://127.0.0.1:8000/api/v1/webhooks/github") (FAIL)
```

| Blocker # | Issue Description | Location | Fix Required |
| :--- | :--- | :--- | :--- |
| **1. Env Var Mismatch** | `netlify.toml` line 11 sets `NEXT_PUBLIC_API_URL`, but `frontend/next.config.mjs` line 9 strictly reads `NEXT_PUBLIC_API_BASE_URL`. | `netlify.toml:11`, `frontend/next.config.mjs:9` | Set `NEXT_PUBLIC_API_BASE_URL` in Netlify dashboard or add fallback in `next.config.mjs`. |
| **2. Build-Time Inlining** | Next.js inlines `NEXT_PUBLIC_*` variables at compile time. If the backend URL is not set in Netlify Environment Variables *before* building, `http://localhost:8000` is permanently baked into the client bundle. | `frontend/lib/api.ts:9` | Configure `NEXT_PUBLIC_API_BASE_URL` in Netlify build environment settings. |
| **3. Hardcoded Connect Button** | The "Connect with GitHub" button hardcodes a browser navigation to localhost. | `frontend/app/connect/page.tsx:237` | Change `http://localhost:8000/auth/github/login` to `${API_BASE_URL}/auth/github/login`. |
| **4. Hardcoded Webhook Fetch** | The "Simulate Real Webhook Ingress" button directly fetches 127.0.0.1. | `frontend/components/RecoveryCompletePanel.tsx:155` | Change `http://127.0.0.1:8000/...` to `${API_BASE_URL}/...`. |
| **5. Backend CORS Origin Rejection** | FastAPI rejects API requests from `https://<site>.netlify.app`. | `backend/main.py:129-140` | Add Netlify domain to `CORS_ORIGINS` in backend environment. |
| **6. Backend OAuth Redirect Loop** | After GitHub authorization, the backend redirects the user to `http://localhost:3000`. | `backend/api/auth.py:173, 184` | Make redirect destination dynamic or configurable via `FRONTEND_URL`. |
| **7. Redundant Build Command & Plugin** | `netlify.toml:3` has `command = "npm install && npm run build"`. Netlify natively runs `npm install`; executing it twice wastes build minutes. Furthermore, `output: "standalone"` in `next.config.mjs` conflicts with Netlify Next plugin v5. | `netlify.toml:3`, `frontend/next.config.mjs:4` | Change build command to `npm run build`. For pure static SPA deployment, `output: 'export'` can be used. |

---

## 10. CHANGE PLAN

Minimal, additive list of edits needed to make the entire stack production-ready on a public domain, ordered by risk (lowest risk / highest priority first). **No UI/design changes.**

```
Priority 1: Critical (Fixes hardcoded localhost references breaking remote users)
    │
Priority 2: High (Fixes CORS, OAuth redirect loops, and environment variable alignment)
    │
Priority 3: Medium (Netlify configuration cleanup and .gitignore leak prevention)
    │
Priority 4: Low (Database architectural hardening)
```

### Risk Level 1: Critical (Direct Functional Blockers)
1. **Fix Hardcoded Login Navigation in Frontend:**
   - **File:** `frontend/app/connect/page.tsx:237`
   - **Edit:** Change `"http://localhost:8000/auth/github/login"` to `${API_BASE_URL}/auth/github/login`.
   - **Rationale:** Prevents remote users from being navigated to their own machine when logging in.
2. **Fix Hardcoded Webhook Ingress Simulation in Frontend:**
   - **File:** `frontend/components/RecoveryCompletePanel.tsx:155`
   - **Edit:** Change `"http://127.0.0.1:8000/api/v1/webhooks/github"` to `${API_BASE_URL}/api/v1/webhooks/github`.
   - **Rationale:** Ensures demo webhook testing hits the deployed backend.
3. **Align Next.js Config API Fallback:**
   - **File:** `frontend/next.config.mjs:9`
   - **Edit:** Change `process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"` to:
     `process.env.NEXT_PUBLIC_API_BASE_URL || process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"`
   - **Rationale:** Prevents silent failures if Netlify injects `NEXT_PUBLIC_API_URL` instead of `NEXT_PUBLIC_API_BASE_URL`.
4. **Fix Backend OAuth Callback Redirects:**
   - **File:** `backend/api/auth.py:173, 184`
   - **Edit:**
     - Line 173: Replace `http://localhost:8000/auth/github/set-cookie?session_id={session_id}` with relative redirect `/auth/github/set-cookie?session_id={session_id}`.
     - Line 184: Replace `http://localhost:3000/detect?session_id={session_id}` with `f"{os.getenv('FRONTEND_URL', 'http://localhost:3000')}/detect?session_id={session_id}"`.
   - **Rationale:** Directs the user back to the deployed Netlify URL post-authentication.

### Risk Level 2: High (CORS, Auth & Environment Configuration)
5. **Add `FRONTEND_URL` to Backend Settings:**
   - **File:** `backend/config/settings.py` and `.env.example`
   - **Edit:** Add `frontend_url: str = Field(default="http://localhost:3000", validation_alias="FRONTEND_URL")`.
   - **Rationale:** Establishes a clean, typed configuration for frontend domain resolution.
6. **Configure Production CORS on Backend:**
   - **File:** Backend runtime environment (e.g., `.env`, Docker Compose, or Cloud Environment Variables)
   - **Edit:** Set `CORS_ORIGINS=https://<your-site>.netlify.app,http://localhost:3000`.
   - **Rationale:** Allows Netlify frontend to call backend endpoints with credentials without CORS preflight blocks.
7. **Configure Production GitHub OAuth Application:**
   - **File:** GitHub Developer Settings
   - **Edit:**
     - Homepage URL: `https://<your-site>.netlify.app`
     - Authorization callback URL: `https://<backend-domain>/auth/github/callback`
     - Update backend env: `GITHUB_REDIRECT_URI=https://<backend-domain>/auth/github/callback`.
   - **Rationale:** Aligns GitHub OAuth with backend callback handlers.

### Risk Level 3: Medium (Netlify Configuration & Secret Leak Prevention)
8. **Update `netlify.toml`:**
   - **File:** `netlify.toml`
   - **Edit:**
     ```toml
     [build]
       base = "frontend"
       command = "npm run build"
       publish = ".next"

     [[plugins]]
       package = "@netlify/plugin-nextjs"

     [build.environment]
       NEXT_PUBLIC_API_BASE_URL = "https://<your-backend-url>"
     ```
   - **Rationale:** Eliminates redundant `npm install` and injects the correct build-time environment variable.
9. **Close `.gitignore` Gaps for SQLite Artifacts:**
   - **File:** `.gitignore`
   - **Edit:** Add:
     ```gitignore
     # SQLite database and WAL/SHM artifacts
     *.db
     *.db-shm
     *.db-wal
     recovery*.db*
     .recovery/
     ```
   - **Rationale:** Prevents accidental commitment of ~150MB of local SQLite test data and engine artifacts.

### Risk Level 4: Low (Architectural Hardening)
10. **Refactor SQLite Hardcoding in `fork_pr.py`:**
    - **File:** `backend/recovery_ext/fork_pr.py:186–206`
    - **Edit:** Replace raw `aiosqlite.connect(DB_PATH)` with standard SQLAlchemy async session (`get_db`) or ensure `DATABASE_PATH` points to a writable persistent volume.
    - **Rationale:** Prevents table initialization errors when deployed against remote PostgreSQL.
11. **Cross-Site Cookie Hardening:**
    - **File:** `backend/api/auth.py:192, 209`
    - **Edit:** When `settings.environment == "production"`, set `samesite="none"` and `secure=True`.
    - **Rationale:** Allows browsers to pass session cookies across distinct domains (Netlify $\leftrightarrow$ Backend Cloud Provider).

---

**Audit Complete.**  
*This report is preserved in `DEPLOY_AUDIT.md`. No application code or project files were altered.*
