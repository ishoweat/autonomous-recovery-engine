from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.abspath("."))

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("live_ci_inventory")

from backend.api.remediate import remediate_code, RemediateRequest
from backend.api.github_workspace import create_pr_endpoint, CreatePrRequest
from backend.services.tavily_evidence import _TAVILY_CACHE

INVENTORY_FAILING_CODE = """function updateInventory(inventory, productId, quantity) {
    const product = inventory.find(item => item.id === productId);

    if (!product) {
        return { success: false, message: "Product not found" };
    }

    product.stock = product.stock - quantity;

    if (product.stock < 0) {
        return { success: false, message: "Insufficient stock" };
    }

    return {
        success: true,
        productId: product.id,
        remainingStock: product.stock
    };
}

const inventory = [
    { id: 101, name: "Laptop", stock: 5 },
    { id: 102, name: "Keyboard", stock: 10 }
];

console.log(updateInventory(inventory, 101, 8));
"""

async def run_live_flow():
    _TAVILY_CACHE.clear()
    
    print("=" * 80)
    print("STARTING LIVE FAILING-CI FLOW: inventoryService.js")
    print("=" * 80)

    # 1. Step 1-9: Remediate (Triage -> Tavily Evidence -> Nemotron -> Patch -> Sandbox -> Risk)
    req = RemediateRequest(
        repoUrl="https://github.com/ishoweat/Bug-testing",
        filePath="inventoryService.js",
        fileContent=INVENTORY_FAILING_CODE,
        errorMessage="AssertionError: State corrupted - product stock was mutated to negative value (-3) when insufficient stock",
        stackTrace="AssertionError: expected inventory[0].stock to equal 5, got -3\n    at test/inventory.test.js:14:12",
        commitSha="6c81035",
    )

    rem_result = await remediate_code(req)

    print("\n--- [STEP 4: TAVILY EVIDENCE STATE] ---")
    ev = rem_result.tavilyEvidence
    print(f"Status: done with {len(ev.get('sources', []))} sources")
    print(f"Confidence: {ev.get('confidence')}")
    print(f"Loop Trail: {ev.get('trail_string')}")

    print("\n--- [STEP 5-7: NEMOTRON & PATCH] ---")
    print(f"Root Cause: {rem_result.rootCause}")
    print(f"Diff:\n{rem_result.diff}")

    print("\n--- [STEP 8-9: SANDBOX & RISK GATE] ---")
    print(f"Sandbox Verified: {rem_result.testResults.get('tests_passed')}")
    print(f"Risk Score: {rem_result.riskAssessment.overall:.4f} ({rem_result.riskAssessment.decision})")

    # 2. Step 10-11: Create PR & Auto-Merge
    print("\n--- [STEP 10-11: GITHUB PR & MERGE] ---")
    pr_req = CreatePrRequest(
        repo="demo/autonomous-recovery-engine",
        filePath="inventoryService.js",
        fixedContent=rem_result.fixedCode,
        incident_id=rem_result.incidentId,
        auto_merge=True,
    )

    pr_res = await create_pr_endpoint(
        request=pr_req,
        session=None,
    )

    print(f"PR URL: {pr_res.pr_url}")
    print(f"PR Number: #{pr_res.pr_number}")
    print(f"Merge Mode: {pr_res.merge_mode} (Merged: {pr_res.merged})")
    print(f"Merge Commit SHA: {pr_res.commit_sha or pr_res.merge_sha}")

    # Print Generated PR Body with Sources
    print("\n" + "=" * 80)
    print("PULL REQUEST BODY (RENDERED WITH SOURCES & CITATIONS)")
    print("=" * 80)
    from backend.integrations.github_pr import build_recovery_pr_body
    pr_body = build_recovery_pr_body(
        incident_id=rem_result.incidentId,
        root_cause={"summary": rem_result.rootCause},
        risk={"score": rem_result.riskAssessment.overall, "decision": rem_result.riskAssessment.decision, "breakdown": [b.explanation for b in rem_result.riskAssessment.breakdown]},
        test_results=rem_result.testResults,
        patch_diff=rem_result.diff,
        evidence=rem_result.tavilyEvidence,
    )
    print(pr_body)

    # 3. Step 12: Post-Merge Verification
    print("\n--- [STEP 12: POST-MERGE VERIFICATION] ---")
    from backend.recovery_ext.post_merge import _run_post_merge_verification
    pm_res = await _run_post_merge_verification(
        incident_id=rem_result.incidentId,
        pr_number=pr_res.pr_number,
        repository_full_name="demo/autonomous-recovery-engine",
        merged_sha=pr_res.commit_sha or "main",
    )
    print(f"Post-Merge Verified Clean: {pm_res.get('tests_passed')} (Exit code: {pm_res.get('exit_code')})")

    return rem_result, pr_res, pm_res

if __name__ == "__main__":
    asyncio.run(run_live_flow())
