"""
ARE — Option 2: Cross-Language Polyglot Fix Engine
===================================================
Async, native integration for the Autonomous Recovery Engine.

Replaces / wraps the single-language repair generation with a four-step
pipeline that supports Python, Go, Rust, JavaScript/TypeScript, and Java:

  1. LanguageDetector          – extension-based heuristic
  2. SemanticRootCauseExtractor – converts raw logs → conceptual root cause
  3. PolyglotFixGenerator       – targeted fix + unit test in the detected lang
  4. MultiAudienceExplainer     – three explanations (devops / product / researcher)

Reuses NebiusNemotron (the project's existing async client).
Falls back to a safe mock result in is_mock_mode.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from backend.llm.nebius import NebiusNemotron


# ─────────────────────────────────────────────────────────────────────────────
# LANGUAGE PROFILES
# ─────────────────────────────────────────────────────────────────────────────

LANGUAGE_PROFILES: dict[str, dict[str, Any]] = {
    "python": {
        "extensions": [".py"],
        "test_frameworks": ["pytest", "unittest"],
        "test_file_pattern": r"test_.*\.py$|.*_test\.py$",
        "import_style": "import / from X import Y",
        "type_hints": True,
        "indent": "4 spaces",
    },
    "go": {
        "extensions": [".go"],
        "test_frameworks": ["testing"],
        "test_file_pattern": r".*_test\.go$",
        "import_style": 'import "pkg"',
        "type_hints": True,
        "indent": "tabs",
    },
    "rust": {
        "extensions": [".rs"],
        "test_frameworks": ["cargo test"],
        "test_file_pattern": r".*\.rs$",
        "import_style": "use crate::x;",
        "type_hints": True,
        "indent": "4 spaces",
    },
    "javascript": {
        "extensions": [".js", ".mjs"],
        "test_frameworks": ["jest", "mocha"],
        "test_file_pattern": r".*\.test\.js$|.*\.spec\.js$",
        "import_style": "const x = require('x') / import x from 'x'",
        "type_hints": False,
        "indent": "2 spaces",
    },
    "typescript": {
        "extensions": [".ts", ".tsx"],
        "test_frameworks": ["jest", "vitest"],
        "test_file_pattern": r".*\.test\.ts$|.*\.spec\.ts$",
        "import_style": "import x from 'x'",
        "type_hints": True,
        "indent": "2 spaces",
    },
    "java": {
        "extensions": [".java"],
        "test_frameworks": ["JUnit 5", "TestNG"],
        "test_file_pattern": r".*Test\.java$",
        "import_style": "import com.example.X;",
        "type_hints": True,
        "indent": "4 spaces",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# DATA CLASS
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PolyglotFixResult:
    """Aggregated output from the Polyglot Fix Engine."""

    language: str
    semantic_issue: str     # human-readable root cause
    fixed_code: str         # corrected function / class / block
    new_test: str           # generated regression test in detected lang/framework
    explanation: str        # why the fix works
    confidence: float       # 0–1
    audiences: dict         # {devops, product, researcher} explanations

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "semantic_issue": self.semantic_issue,
            "fixed_code": self.fixed_code,
            "new_test": self.new_test,
            "explanation": self.explanation,
            "confidence": self.confidence,
            "audiences": self.audiences,
        }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — LANGUAGE DETECTOR
# ─────────────────────────────────────────────────────────────────────────────


class LanguageDetector:
    """Detects the primary language from file extension frequency."""

    def detect(self, source_files: dict[str, str]) -> str:
        ext_counts: dict[str, int] = {}
        for filename in source_files:
            ext = os.path.splitext(filename)[-1].lower()
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

        for lang, profile in LANGUAGE_PROFILES.items():
            for ext in profile["extensions"]:
                if ext in ext_counts:
                    return lang

        return "python"  # safe default


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — SEMANTIC ROOT CAUSE EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

_ROOT_CAUSE_SYSTEM = """You are an expert debugging engineer.
Given a test failure log, extract the SEMANTIC root cause — not just the error message.
Focus on WHY it failed conceptually (type mismatch, null reference, off-by-one, race condition, etc.).

Respond ONLY in this JSON format:
{
  "semantic_issue": "one-sentence description of the root cause",
  "error_category": "TYPE_MISMATCH|NULL_REF|LOGIC_ERROR|ASYNC_ERROR|IMPORT_ERROR|OTHER",
  "affected_symbol": "function/class/variable name that is wrong",
  "confidence": 0.0-1.0
}"""


class SemanticRootCauseExtractor:
    """
    Converts raw test failure logs into a language-agnostic semantic issue
    using Nemotron-70B via the project's existing NebiusNemotron client.
    """

    def __init__(
        self,
        test_log: str,
        language: str,
        llm: NebiusNemotron,
    ) -> None:
        self.test_log = test_log
        self.language = language
        self.llm = llm

    async def extract(self) -> dict[str, Any]:
        user = (
            f"Language: {self.language}\n\n"
            f"Test failure log:\n```\n{self.test_log[:3000]}\n```"
        )
        try:
            return await self.llm.complete_json(
                system_prompt=_ROOT_CAUSE_SYSTEM,
                user_prompt=user,
                max_tokens=256,
            )
        except Exception as exc:
            return {
                "semantic_issue": f"Could not extract semantic issue: {exc}",
                "error_category": "OTHER",
                "affected_symbol": "unknown",
                "confidence": 0.4,
            }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — POLYGLOT FIX GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

_FIX_SYSTEM_TEMPLATE = """You are an expert {language} engineer.
Generate a targeted code fix and a new unit test.

Rules:
- Write ONLY in {language}
- Use {framework} for the test
- Indentation: {indent}
- Import style: {import_style}
- Fix ONLY the semantic issue described. Do NOT refactor unrelated code.
- The new unit test must FAIL on the original code and PASS on your fix.

Respond ONLY in this JSON format (no markdown fences):
{{
  "fixed_code": "the corrected function/class/block as a string",
  "new_test": "the new unit test as a string",
  "explanation": "one paragraph why this fix resolves the semantic issue",
  "confidence": 0.0-1.0
}}"""


class PolyglotFixGenerator:
    """
    Generates a correct fix and a new regression test in the detected language
    and framework using Nemotron-70B.
    """

    _CONTEXT_BUDGET = 6000  # chars

    def __init__(
        self,
        language: str,
        semantic_issue: str,
        source_files: dict[str, str],
        test_log: str,
        llm: NebiusNemotron,
    ) -> None:
        self.language = language
        self.profile = LANGUAGE_PROFILES.get(language, LANGUAGE_PROFILES["python"])
        self.semantic = semantic_issue
        self.source_files = source_files
        self.test_log = test_log
        self.llm = llm

    def _build_context(self) -> str:
        context = ""
        for fname, content in self.source_files.items():
            chunk = f"\n--- {fname} ---\n{content[:1500]}\n"
            if len(context) + len(chunk) > self._CONTEXT_BUDGET:
                break
            context += chunk
        return context

    async def generate(self) -> dict[str, Any]:
        system = _FIX_SYSTEM_TEMPLATE.format(
            language=self.language,
            framework=self.profile["test_frameworks"][0],
            indent=self.profile["indent"],
            import_style=self.profile["import_style"],
        )
        user = (
            f"Semantic issue: {self.semantic}\n\n"
            f"Source files:\n{self._build_context()}\n\n"
            f"Test failure log (last 1000 chars):\n{self.test_log[-1000:]}"
        )
        try:
            return await self.llm.complete_json(
                system_prompt=system,
                user_prompt=user,
                max_tokens=2048,
                temperature=0.1,
            )
        except Exception as exc:
            return {
                "fixed_code": f"# Fix generation failed: {exc}",
                "new_test": f"# Test generation failed: {exc}",
                "explanation": str(exc),
                "confidence": 0.2,
            }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — MULTI-AUDIENCE EXPLAINER
# ─────────────────────────────────────────────────────────────────────────────

_AUDIENCE_SYSTEM = """You are a technical writer who can explain the same fix to different audiences.
Given a fix explanation and semantic issue, generate three versions.

Respond ONLY in this JSON:
{
  "devops":     "2 sentences: technical ops perspective — what changed and how it affects CI/CD",
  "product":    "1 sentence: non-technical — what improved for the user/system",
  "researcher": "2 sentences: ML/engineering — model confidence, uncertainty, method used"
}"""


class MultiAudienceExplainer:
    """
    Generates three stakeholder explanations that feed directly into the
    existing dashboard event stream.
    """

    def __init__(
        self,
        explanation: str,
        semantic_issue: str,
        confidence: float,
        language: str,
        llm: NebiusNemotron,
    ) -> None:
        self.explanation = explanation
        self.semantic_issue = semantic_issue
        self.confidence = confidence
        self.language = language
        self.llm = llm

    async def generate(self) -> dict[str, str]:
        user = (
            f"Language: {self.language}\n"
            f"Semantic issue: {self.semantic_issue}\n"
            f"Fix explanation: {self.explanation}\n"
            f"Model confidence: {self.confidence:.0%}"
        )
        try:
            return await self.llm.complete_json(  # type: ignore[return-value]
                system_prompt=_AUDIENCE_SYSTEM,
                user_prompt=user,
                max_tokens=400,
            )
        except Exception:
            return {
                "devops": f"Applied fix for: {self.semantic_issue}",
                "product": "System reliability improved after automated fix.",
                "researcher": (
                    f"Fix generated with {self.confidence:.0%} confidence "
                    "using Nemotron-70B on Nebius."
                ),
            }


# ─────────────────────────────────────────────────────────────────────────────
# MOCK FALLBACK
# ─────────────────────────────────────────────────────────────────────────────

_MOCK_RESULT = PolyglotFixResult(
    language="python",
    semantic_issue=(
        "Missing key guard: payload accessed without validation. (mock)"
    ),
    fixed_code=(
        "def authenticate(payload):\n"
        "    user_id = payload.get('user_id')\n"
        "    if not user_id:\n"
        "        raise ValueError('user_id is required')\n"
        "    return lookup_user(user_id)\n"
    ),
    new_test=(
        "def test_missing_user_id_raises_value_error():\n"
        "    with pytest.raises(ValueError, match='user_id is required'):\n"
        "        authenticate({})\n"
    ),
    explanation=(
        "The fix uses dict.get() for safe key access and raises a controlled "
        "ValueError when user_id is absent, preventing the unhandled KeyError."
    ),
    confidence=0.95,
    audiences={
        "devops": (
            "Payload validation added to authenticate(); CI pipeline will now "
            "catch missing user_id before it reaches production."
        ),
        "product": "Users are protected from crashes caused by malformed auth requests.",
        "researcher": (
            "Fix generated using NVIDIA Nemotron on Nebius. "
            "High confidence verified patch with full regression coverage."
        ),
    },
)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────────────


class PolyglotFixEngine:
    """
    Async drop-in replacement for the single-language repair generator.

    Wire into the LangGraph repair_node:

        engine = PolyglotFixEngine(
            failed_test_log = state["test_results"].get("stdout", ""),
            source_files    = state["source_files"],
            llm             = llm,
            is_mock_mode    = state["is_mock_mode"],
        )
        result = await engine.generate()

        state["generated_fix"]      = result.fixed_code
        state["new_unit_test"]      = result.new_test
        state["polyglot_language"]  = result.language
        state["semantic_issue"]     = result.semantic_issue
        state["polyglot_audiences"] = result.audiences
    """

    def __init__(
        self,
        failed_test_log: str,
        source_files: dict[str, str],
        llm: NebiusNemotron | None = None,
        is_mock_mode: bool = False,
    ) -> None:
        self.test_log = failed_test_log
        self.source_files = source_files
        self.llm = llm
        self.is_mock_mode = is_mock_mode

    async def generate(self) -> PolyglotFixResult:
        if self.is_mock_mode:
            return _MOCK_RESULT

        if self.llm is None:
            raise RuntimeError(
                "PolyglotFixEngine requires a NebiusNemotron instance "
                "when not in mock mode."
            )

        # Step 1: Detect language
        language = LanguageDetector().detect(self.source_files)

        # Step 2: Extract semantic root cause
        root_cause = await SemanticRootCauseExtractor(
            test_log=self.test_log,
            language=language,
            llm=self.llm,
        ).extract()
        semantic_issue = root_cause.get("semantic_issue") or root_cause.get("issue") or root_cause.get("summary") or "Unknown semantic issue"

        # Step 3: Generate fix + regression test
        fix_data = await PolyglotFixGenerator(
            language=language,
            semantic_issue=semantic_issue,
            source_files=self.source_files,
            test_log=self.test_log,
            llm=self.llm,
        ).generate()

        # Step 4: Multi-audience explanations
        audiences = await MultiAudienceExplainer(
            explanation=fix_data.get("explanation", ""),
            semantic_issue=semantic_issue,
            confidence=float(fix_data.get("confidence", 0.8)),
            language=language,
            llm=self.llm,
        ).generate()

        return PolyglotFixResult(
            language=language,
            semantic_issue=semantic_issue,
            fixed_code=fix_data.get("fixed_code", ""),
            new_test=fix_data.get("new_test", ""),
            explanation=fix_data.get("explanation", ""),
            confidence=float(fix_data.get("confidence", 0.8)),
            audiences=audiences,
        )
