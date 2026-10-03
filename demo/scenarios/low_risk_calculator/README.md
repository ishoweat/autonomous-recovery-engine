# Low Risk Calculator
A simple math library.

## Bug
The `divide` function lacks a zero check, throwing a ZeroDivisionError.
Fix is a one line `if b == 0: return 0` or similar.

## Expected Decision: ALLOW
- File Criticality: 0.10 (Not critical)
- Change Scope: 0.05 (1 file)
- Security Sensitivity: 0.05 (Not sensitive)
- Diff Complexity: 0.04 (<=4 lines)
- Total Score: 0.24 -> ALLOW (< 0.3)
