# Phase 2: LLM Analysis & Patch Generation

## Objectives
- Integrate Nemotron for root-cause analysis and patch generation.
- Enforce strict test-tampering and path-traversal protection server-side.

## Required Changes

| Component | Path:Line | Current State | Required Update |
|---|---|---|---|
| Target Context | `backend/orchestration/nodes.py:829` | `affected_file` is extracted from state. | Add validation ensuring `affected_file` is within repository bounds and is NOT a test/CI file. If invalid, emit `UNSUPPORTED_FAILURE`. |
| Patch Integrity | `backend/orchestration/nodes.py:930` | Patch string is extracted without path/content validation. | Introduce server-side diff parser to extract all modified paths. Reject diffs modifying `tests/**`, `test/**`, `test_*.py`, `*_test.py`, `*.spec.*`, `*.test.*`, `conftest.py`, `pytest.ini`, `tox.ini`, `.github/workflows/**`. |
| Path Normalization | `backend/orchestration/nodes.py:930` | No path normalization applied to the diff. | Reject diffs containing `../`, symlinks, or deletions/renames of protected files. |
| Test-Gaming Guards | `backend/orchestration/nodes.py:930` | Generated patch accepted blindly. | Scan generated `fixed_code` for test-gaming patterns: `pytest.skip`, `pytest.xfail`, `sys.exit`, or hardcoded test literals. |

## Acceptance Criteria
- [ ] Pipeline strictly rejects patches attempting to modify test or CI config files.
- [ ] Path traversal vectors (`../`) in diffs are blocked.
- [ ] Model successfully generates source-only patches for identified application defects.
