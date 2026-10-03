# Medium Risk Data Pipeline

## Bug
The `process_records` function has a bug that skips the last record in a batch or drops valid rows.
Fix requires multiple lines of change (5-10 lines).

## Expected Decision: APPROVE
- File Criticality: 0.10 (Not critical)
- Change Scope: 0.05 (1 file)
- Security Sensitivity: 0.05 (Not sensitive)
- Diff Complexity: 0.10 (5-10 lines)
- Total Score: 0.30 -> APPROVE (0.3 - 0.7)
