import os
import json
import pytest
from backend.orchestration.risk import calculate_patch_risk

def test_low_risk_scenario():
    # 1 file, 1 line diff, no sensitive path
    os.environ.pop("FORCE_RISK_SCORE", None)
    os.environ["CRITICAL_PATHS_JSON"] = json.dumps({"auth/**": 0.50, "payments/**": 0.60})
    files = ["demo/scenarios/low_risk_calculator/calculator.py"]
    patch_diff = """--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,4 @@
 def divide(a, b):
+    if b == 0:
+        return 0
     return a / b
"""
    result = calculate_patch_risk(files=files, patch_diff=patch_diff)
    assert result["decision"] == "ALLOW"
    assert result["score"] < 0.30

def test_medium_risk_scenario():
    # 1 file, 6 lines diff, no sensitive path
    os.environ.pop("FORCE_RISK_SCORE", None)
    os.environ["CRITICAL_PATHS_JSON"] = json.dumps({"auth/**": 0.50, "payments/**": 0.60})
    files = ["demo/scenarios/medium_risk_data_pipeline/pipeline.py"]
    patch_diff = """--- a/pipeline.py
+++ b/pipeline.py
@@ -1,5 +1,11 @@
 def process_records(records):
     processed = []
-    for i in range(len(records) - 1):
+    for i in range(len(records)):
+        if not records:
+            break
+        if not records[i]:
+            continue
         record = records[i]
         if record.get("status") == "active":
             record["processed"] = True
"""
    result = calculate_patch_risk(files=files, patch_diff=patch_diff)
    assert result["decision"] == "APPROVE", f"Score was {result['score']}"
    assert 0.30 <= result["score"] <= 0.70

def test_high_risk_scenario():
    # 2 files, 15 lines diff, auth/ matching sensitive path and critical path
    os.environ.pop("FORCE_RISK_SCORE", None)
    os.environ["CRITICAL_PATHS_JSON"] = json.dumps({"auth/**": 0.50, "payments/**": 0.60})
    files = [
        "demo/scenarios/high_risk_auth_payments/auth/payments.py",
        "demo/scenarios/high_risk_auth_payments/test_payments.py"
    ]
    # Simulate a larger patch to ensure complexity score is higher
    patch_diff = """--- a/auth/payments.py
+++ b/auth/payments.py
@@ -1,5 +1,15 @@
+import hashlib
+import time
+
 def verify_payment(token: str, amount: float) -> bool:
-    if not token:
+    if not token or not token.startswith("tok_"):
         return False
+        
+    parts = token.split("_")
+    if len(parts) != 3:
+        return False
+        
+    if int(parts[2]) < time.time() - 3600:
+        return False
         
     return True
"""
    result = calculate_patch_risk(files=files, patch_diff=patch_diff)
    assert result["decision"] == "BLOCK"
    assert result["score"] > 0.70
