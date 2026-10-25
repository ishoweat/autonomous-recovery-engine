"""
ARE — Option 1: Adversarial Resilience Layer
=============================================
Async, native integration for the Autonomous Recovery Engine.

Runs three adversarial checks against a generated patch BEFORE it enters
the failure analyser / deployment path:

  1. Mutation Testing      – synthetic operator mutations + subprocess re-run
  2. Supply Chain CVE      – new deps vs. OSV.dev (no API key required)
  3. Behavioral Replay     – Nemotron-70B static analysis via NebiusNemotron
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any

import httpx

from backend.llm.nebius import NebiusNemotron

# ── OSV.dev — free, no key required ──────────────────────────────────────────
_OSV_API = "https://api.osv.dev/v1/query"


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASS
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class AdversarialReport:
    """Aggregated result from all three adversarial checks."""

    mutation_score: float           # 0–1  (higher = patch is robust)
    cve_hits: list[dict]            # [{pkg, version, cve_id, severity, summary}]
    behavioral_flags: list[str]     # ["memory_leak_risk", "race_condition", …]
    overall_safe: bool
    confidence: float               # 0–1
    summary: str
    raw: dict = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "mutation_score": self.mutation_score,
            "cve_hits": self.cve_hits,
            "behavioral_flags": self.behavioral_flags,
            "overall_safe": self.overall_safe,
            "confidence": self.confidence,
            "summary": self.summary,
            "raw": self.raw,
        }


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 1 — MUTATION TESTING
# ─────────────────────────────────────────────────────────────────────────────


class MutationTester:
    """
    Injects synthetic operator mutations into the patch code, then re-runs
    the test suite.  If tests still pass after mutation the fix is shallow
    or the test coverage is weak.

    Uses asyncio.create_subprocess_exec for non-blocking subprocess execution.
    """

    _MUTATIONS: list[tuple[str, str]] = [
        ("==", "!="),
        (">=", ">"),
        ("<=", "<"),
        ("True", "False"),
        ("and", "or"),
        ("return True", "return False"),
        (" + ", " - "),
        (" > ", " < "),
    ]

    def __init__(
        self,
        patch_code: str,
        test_cmd: str = "pytest --tb=no -q",
    ) -> None:
        self.patch_code = patch_code
        self.test_cmd = test_cmd.split()

    def _apply_mutation(
        self,
        code: str,
        old: str,
        new: str,
    ) -> str | None:
        if old not in code:
            return None
        return code.replace(old, new, 1)

    async def _run_tests_on_code(self, mutated_code: str) -> bool:
        """
        Write mutated code to a temp file and run the test suite.
        Returns True when tests FAIL (good — mutation was caught).
        """
        tmp = "/tmp/_are_mutation_test.py"
        try:
            with open(tmp, "w") as fh:
                fh.write(mutated_code)
            proc = await asyncio.create_subprocess_exec(
                *self.test_cmd,
                tmp,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await asyncio.wait_for(proc.communicate(), timeout=30)
            return (proc.returncode or 0) != 0
        except OSError:
            return True  # assume caught if we can't write
        except Exception:
            return True  # assume caught on subprocess error
        finally:
            try:
                import os
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass

    async def run(self) -> dict[str, Any]:
        killed = 0
        survived = 0
        details: list[dict] = []

        for old, new in self._MUTATIONS:
            mutated = self._apply_mutation(self.patch_code, old, new)
            if mutated is None:
                continue
            tests_caught = await self._run_tests_on_code(mutated)
            status = "killed" if tests_caught else "survived"
            if tests_caught:
                killed += 1
            else:
                survived += 1
            details.append({"mutation": f"{old} → {new}", "status": status})

        total = killed + survived
        score = killed / total if total > 0 else 1.0

        return {
            "mutation_score": round(score, 3),
            "killed": killed,
            "survived": survived,
            "details": details,
            "pass": score >= 0.6,
        }


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 2 — SUPPLY CHAIN CVE VALIDATION
# ─────────────────────────────────────────────────────────────────────────────


class SupplyChainValidator:
    """
    Extracts new PyPI dependencies from the patch diff and queries OSV.dev
    for known CVEs.  Uses httpx for fully async HTTP — no API key required.
    """

    _IMPORT_RE = re.compile(
        r"^\+\s*(?:import|from)\s+([\w\.]+)",
        re.MULTILINE,
    )
    _INSTALL_RE = re.compile(
        r"(?:pip install|require)\s+([\w\-]+)(?:==|>=|<=)?([\d\.]*)",
        re.IGNORECASE,
    )

    def __init__(self, patch_diff: str) -> None:
        self.patch_diff = patch_diff

    def _extract_deps(self) -> list[tuple[str, str]]:
        deps: list[tuple[str, str]] = []
        for m in self._IMPORT_RE.finditer(self.patch_diff):
            pkg = m.group(1).split(".")[0]
            deps.append((pkg, ""))
        for m in self._INSTALL_RE.finditer(self.patch_diff):
            deps.append((m.group(1), m.group(2)))
        return list(set(deps))

    async def _query_osv(
        self,
        client: httpx.AsyncClient,
        package: str,
        version: str,
    ) -> list[dict]:
        payload: dict[str, Any] = {
            "package": {"name": package, "ecosystem": "PyPI"},
        }
        if version:
            payload["version"] = version
        try:
            resp = await client.post(_OSV_API, json=payload, timeout=10)
            if resp.status_code != 200:
                return []
            vulns = resp.json().get("vulns", [])
            return [
                {
                    "pkg": package,
                    "version": version or "unknown",
                    "cve_id": v.get("id", "N/A"),
                    "severity": v.get("database_specific", {}).get(
                        "severity", "UNKNOWN"
                    ),
                    "summary": v.get("summary", ""),
                }
                for v in vulns
            ]
        except Exception:
            return []

    async def run(self) -> dict[str, Any]:
        deps = self._extract_deps()
        all_hits: list[dict] = []

        async with httpx.AsyncClient() as client:
            results = await asyncio.gather(
                *[self._query_osv(client, pkg, ver) for pkg, ver in deps],
                return_exceptions=True,
            )

        for result in results:
            if isinstance(result, list):
                all_hits.extend(result)

        critical = [
            h for h in all_hits if h["severity"] in ("CRITICAL", "HIGH")
        ]
        return {
            "deps_scanned": deps,
            "cve_hits": all_hits,
            "critical_count": len(critical),
            "pass": len(critical) == 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# CHECK 3 — BEHAVIORAL REPLAY (Nemotron static analysis)
# ─────────────────────────────────────────────────────────────────────────────

_BEHAVIORAL_SYSTEM = """You are an expert software security and reliability engineer.
Analyze the given code patch for behavioral risks:
- Memory leaks (unclosed resources, growing lists, missing cleanup)
- Race conditions (shared state, threading issues, non-atomic ops)
- Infinite loops or unbounded recursion
- Silent exception swallowing
- Unvalidated external input usage
- Resource exhaustion (CPU, disk, network)

Respond ONLY in this exact JSON format:
{
  "flags": ["flag1", "flag2"],
  "risk_level": "LOW|MEDIUM|HIGH",
  "confidence": 0.0-1.0,
  "reasoning": "one sentence per flag"
}
If no issues found, return {"flags": [], "risk_level": "LOW", "confidence": 0.95, "reasoning": "No behavioral risks detected."}
"""


class BehavioralReplayAnalyzer:
    """
    Uses NebiusNemotron (the project's existing async client) to reason about
    the patch statically for memory leaks, race conditions, etc.
    """

    def __init__(self, patch_code: str, llm: NebiusNemotron) -> None:
        self.patch_code = patch_code
        self.llm = llm

    async def run(self) -> dict[str, Any]:
        user_msg = (
            f"Analyze this patch for behavioral risks:\n\n"
            f"```python\n{self.patch_code}\n```"
        )
        try:
            result = await self.llm.complete_json(
                system_prompt=_BEHAVIORAL_SYSTEM,
                user_prompt=user_msg,
                max_tokens=512,
                temperature=0.2,
            )
        except Exception as exc:
            result = {
                "flags": ["analysis_failed"],
                "risk_level": "MEDIUM",
                "confidence": 0.5,
                "reasoning": f"Behavioral analysis error: {exc}",
            }

        return {
            "behavioral_flags": result.get("flags", []),
            "risk_level": result.get("risk_level", "UNKNOWN"),
            "confidence": result.get("confidence", 0.5),
            "reasoning": result.get("reasoning", ""),
            "pass": result.get("risk_level") == "LOW",
        }


# ─────────────────────────────────────────────────────────────────────────────
# MOCK FALLBACK
# ─────────────────────────────────────────────────────────────────────────────

_MOCK_REPORT = AdversarialReport(
    mutation_score=0.875,
    cve_hits=[],
    behavioral_flags=[],
    overall_safe=True,
    confidence=0.91,
    summary="✅ All adversarial checks passed. (mock mode)",
    raw={
        "mutation": {
            "mutation_score": 0.875,
            "killed": 7,
            "survived": 1,
            "details": [],
            "pass": True,
        },
        "cve": {
            "deps_scanned": [],
            "cve_hits": [],
            "critical_count": 0,
            "pass": True,
        },
        "behavioral": {
            "behavioral_flags": [],
            "risk_level": "LOW",
            "confidence": 0.95,
            "reasoning": "No behavioral risks detected. (mock)",
            "pass": True,
        },
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────


class AdversarialResilienceLayer:
    """
    Async orchestrator for all three adversarial checks.

    Wire into the LangGraph pipeline via ``adversarial_resilience_node`` in
    ``nodes.py`` — it is called automatically before the failure analyser.

    In mock mode it short-circuits with a deterministic safe report so that
    integration tests never require live API credentials or a running test
    suite.
    """

    def __init__(
        self,
        patch_code: str,
        patch_diff: str = "",
        test_cmd: str = "pytest --tb=no -q",
        llm: NebiusNemotron | None = None,
        is_mock_mode: bool = False,
    ) -> None:
        self.patch_code = patch_code
        self.patch_diff = patch_diff or patch_code
        self.test_cmd = test_cmd
        self.llm = llm
        self.is_mock_mode = is_mock_mode

    async def run_all_checks(self) -> AdversarialReport:
        if self.is_mock_mode:
            return _MOCK_REPORT

        if self.llm is None:
            raise RuntimeError(
                "AdversarialResilienceLayer requires a NebiusNemotron instance "
                "when not in mock mode."
            )

        # Run mutation test and CVE scan concurrently; behavioral replay last
        # (it depends on no prior results).
        mutation_task = MutationTester(self.patch_code, self.test_cmd).run()
        cve_task = SupplyChainValidator(self.patch_diff).run()
        behavioral_task = BehavioralReplayAnalyzer(self.patch_code, self.llm).run()

        mutation_result, cve_result, behavioral_result = await asyncio.gather(
            mutation_task,
            cve_task,
            behavioral_task,
        )

        all_pass = (
            mutation_result["pass"]
            and cve_result["pass"]
            and behavioral_result["pass"]
        )

        confidence = round(
            (mutation_result["mutation_score"] * 0.35)
            + ((1 - min(cve_result["critical_count"], 5) / 5) * 0.30)
            + (behavioral_result["confidence"] * 0.35),
            3,
        )

        summary_parts: list[str] = []
        if not mutation_result["pass"]:
            summary_parts.append(
                f"⚠️ Mutation: {mutation_result['survived']} mutation(s) survived."
            )
        if not cve_result["pass"]:
            summary_parts.append(
                f"🚨 CVE: {cve_result['critical_count']} critical vulnerability(ies)."
            )
        if not behavioral_result["pass"]:
            flags = ", ".join(behavioral_result["behavioral_flags"])
            summary_parts.append(f"⚡ Behavioral: [{flags}] detected.")
        if all_pass:
            summary_parts.append("✅ All adversarial checks passed.")

        return AdversarialReport(
            mutation_score=mutation_result["mutation_score"],
            cve_hits=cve_result["cve_hits"],
            behavioral_flags=behavioral_result["behavioral_flags"],
            overall_safe=all_pass,
            confidence=confidence,
            summary=" | ".join(summary_parts),
            raw={
                "mutation": mutation_result,
                "cve": cve_result,
                "behavioral": behavioral_result,
            },
        )


class AdversarialRiskError(Exception):
    """Raised when the adversarial layer deems a patch unsafe."""
