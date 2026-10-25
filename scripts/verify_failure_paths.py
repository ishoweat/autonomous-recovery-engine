from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath("."))

from backend.api.remediate import remediate_code, RemediateRequest
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
"""

async def run_failure_path_checks():
    print("=" * 80)
    print("TESTING FAILURE PATH 1: TEMPORARILY UNSET TAVILY_API_KEY")
    print("=" * 80)

    original_key = os.environ.get("TAVILY_API_KEY", "tvly-live-research-active")
    if "TAVILY_API_KEY" in os.environ:
        del os.environ["TAVILY_API_KEY"]
    _TAVILY_CACHE.clear()

    req1 = RemediateRequest(
        repoUrl="https://github.com/ishoweat/Bug-testing",
        filePath="inventoryService.js",
        fileContent=INVENTORY_FAILING_CODE,
        errorMessage="AssertionError: State corrupted - product stock was mutated to negative value (-3) when insufficient stock",
        stackTrace="AssertionError: expected inventory[0].stock to equal 5, got -3\n    at test/inventory.test.js:14:12",
    )

    res1 = await remediate_code(req1)
    conf1 = res1.tavilyEvidence.get("confidence") if res1.tavilyEvidence else "none"
    sources1 = res1.tavilyEvidence.get("sources", []) if res1.tavilyEvidence else []
    risk1 = res1.riskAssessment.overall
    decision1 = res1.riskAssessment.decision

    print(f"Pipeline Completed: YES (incidentId: {res1.incidentId})")
    print(f"Tavily Confidence: {conf1}")
    print(f"Sources Count: {len(sources1)}")
    print(f"Risk Score: {risk1:.4f} (Decision: {decision1})")

    assert conf1 == "none", f"Expected confidence none, got {conf1}"
    assert len(sources1) == 0, f"Expected 0 sources, got {len(sources1)}"
    assert risk1 >= 0.45, f"Expected risk >= 0.45, got {risk1}"
    assert decision1 == "APPROVE", f"Expected decision APPROVE, got {decision1}"
    print(">>> PASS: Unset API key completes gracefully with confidence=none and elevated risk.\n")

    # RESTORE API KEY
    os.environ["TAVILY_API_KEY"] = original_key
    print(f"Restored TAVILY_API_KEY in environment.")

    print("\n" + "=" * 80)
    print("TESTING FAILURE PATH 2: SIMULATE FORCED TAVILY TIMEOUT")
    print("=" * 80)

    os.environ["FORCE_TAVILY_TIMEOUT"] = "true"
    _TAVILY_CACHE.clear()

    req2 = RemediateRequest(
        repoUrl="https://github.com/ishoweat/Bug-testing",
        filePath="inventoryService.js",
        fileContent=INVENTORY_FAILING_CODE,
        errorMessage="AssertionError: State corrupted - product stock was mutated to negative value (-3) when insufficient stock",
        stackTrace="AssertionError: expected inventory[0].stock to equal 5, got -3\n    at test/inventory.test.js:14:12",
    )

    res2 = await remediate_code(req2)
    conf2 = res2.tavilyEvidence.get("confidence") if res2.tavilyEvidence else "none"
    sources2 = res2.tavilyEvidence.get("sources", []) if res2.tavilyEvidence else []
    risk2 = res2.riskAssessment.overall
    decision2 = res2.riskAssessment.decision

    print(f"Pipeline Completed: YES (incidentId: {res2.incidentId})")
    print(f"Tavily Confidence: {conf2}")
    print(f"Sources Count: {len(sources2)}")
    print(f"Risk Score: {risk2:.4f} (Decision: {decision2})")

    assert conf2 == "none", f"Expected confidence none, got {conf2}"
    assert len(sources2) == 0, f"Expected 0 sources, got {len(sources2)}"
    assert risk2 >= 0.45, f"Expected risk >= 0.45, got {risk2}"
    assert decision2 == "APPROVE", f"Expected decision APPROVE, got {decision2}"
    print(">>> PASS: Simulated timeout completes gracefully with confidence=none and elevated risk.\n")

    del os.environ["FORCE_TAVILY_TIMEOUT"]
    _TAVILY_CACHE.clear()

if __name__ == "__main__":
    asyncio.run(run_failure_path_checks())
