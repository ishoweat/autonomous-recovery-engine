#!/usr/bin/env python3
"""
scripts/demo_high_risk.py
─────────────────────────
Demo helper for Phase 5 BLOCK path.

Usage:
    # Basic demo (uses test server on localhost:8000):
    python scripts/demo_high_risk.py

    # Custom server URL:
    python scripts/demo_high_risk.py --url http://localhost:8001

    # With real repository (creates a GitHub issue):
    GITHUB_TOKEN=ghp_xxx python scripts/demo_high_risk.py --repo owner/repo

Environment Variables
─────────────────────
FORCE_RISK_SCORE    Set to a float > 0.7 to force the BLOCK path.
                    Default: 0.85
ENABLE_BLOCK_ESCALATION  Must be "true" for full Phase 5 behavior.

Notes
─────
- Never include real secrets in the payload. 
- The GITHUB_TOKEN is read server-side from the environment; this script
  does NOT transmit it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def _print_banner():
    print(f"\n{BOLD}{RED}╔═══════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{RED}║  Phase 5: BLOCK Path Demo — High Risk Score        ║{RESET}")
    print(f"{BOLD}{RED}╚═══════════════════════════════════════════════════╝{RESET}\n")


def _post(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read())
            return resp.status, body
    except urllib.error.HTTPError as e:
        body = json.loads(e.read())
        return e.code, body


def _get(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo Phase 5 BLOCK path")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--repo", default="", help="GitHub repo full name (owner/repo)")
    args = parser.parse_args()

    base = args.url.rstrip("/")
    repo = args.repo or os.environ.get("DEMO_REPO", "Sahil707-pop/third-ai-testing")

    _print_banner()

    force_score = float(os.environ.get("FORCE_RISK_SCORE", "0.85"))
    print(f"{CYAN}Step 1: Verify configuration{RESET}")
    print(f"  FORCE_RISK_SCORE      = {YELLOW}{force_score}{RESET}")
    print(f"  ENABLE_BLOCK_ESCALATION = {YELLOW}{os.environ.get('ENABLE_BLOCK_ESCALATION', '(not set, set to true on server)')}{RESET}")
    print(f"  Target repository     = {YELLOW}{repo}{RESET}")
    print()

    if force_score <= 0.7:
        print(f"{RED}⚠  FORCE_RISK_SCORE={force_score} is <= 0.7. Set it to > 0.7 to trigger BLOCK.{RESET}")
        print(f"   Example: FORCE_RISK_SCORE=0.85 python scripts/demo_high_risk.py")
        sys.exit(1)

    incident_id = f"demo-block-{int(time.time())}"
    print(f"{CYAN}Step 2: Submit a scan (incident_id={incident_id}){RESET}")

    payload = {
        "incident_id": incident_id,
        "repository_url": f"https://github.com/{repo}",
        "repository_full_name": repo,
        "source_branch": "main",
        "commit_sha": "demo000",
        "error_message": "ZeroDivisionError: division by zero — demo for Phase 5 BLOCK path",
        "stack_trace": "File 'calculator.py', line 5, in calculate_average\n  return total / len(numbers)",
        "file_path": "calculator.py",
        "trigger": "demo_script",
    }

    status, body = _post(f"{base}/api/v1/incident/run", payload)
    if status not in (200, 201, 202):
        print(f"{RED}✗ POST /api/v1/incident/run returned {status}: {body}{RESET}")
        print(f"\n{YELLOW}Tip: Ensure the backend is running and FORCE_RISK_SCORE={force_score} is exported.{RESET}")
        sys.exit(1)

    print(f"{GREEN}✓ Scan submitted (status={status}){RESET}")
    print(f"  Response: {json.dumps(body, indent=2)[:300]}")
    print()

    # Poll incident status
    print(f"{CYAN}Step 3: Poll incident status (up to 60s){RESET}")
    deadline = time.time() + 60
    final_status = None
    while time.time() < deadline:
        _, inc = _get(f"{base}/api/incidents/{incident_id}")
        final_status = inc.get("status", "unknown")
        decision = inc.get("action_decision", "—")
        issue_url = inc.get("escalation_issue_url") or inc.get("issue_url") or ""
        print(f"  status={final_status}  decision={decision}  issue={issue_url or '(none yet)'}")
        if final_status in ("failed", "escalated", "recovered"):
            break
        time.sleep(4)

    print()
    if final_status == "failed":
        print(f"{GREEN}{BOLD}✓ BLOCK path confirmed: incident status = FAILED{RESET}")
        if issue_url:
            print(f"{GREEN}✓ GitHub issue created: {issue_url}{RESET}")
        else:
            print(f"{YELLOW}⚠  No GitHub issue URL found (ENABLE_BLOCK_ESCALATION may be false or GitHub not configured){RESET}")
    else:
        print(f"{YELLOW}⚠  Incident status = {final_status} (expected 'failed' for BLOCK path){RESET}")

    # Check blocked count in ROI
    print()
    print(f"{CYAN}Step 4: Check ROI blocked incidents counter{RESET}")
    _, roi = _get(f"{base}/api/v1/roi/blocked-incidents")
    blocked = roi.get("blocked_incidents", "N/A")
    print(f"{GREEN}  Blocked incidents: {blocked}{RESET}")

    print(f"\n{BOLD}Demo complete. To reset, reload the Mission Control UI.{RESET}\n")
    print(f"{YELLOW}Reminder: unset FORCE_RISK_SCORE to restore normal operation.{RESET}\n")


if __name__ == "__main__":
    main()
