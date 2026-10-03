import asyncio
import os
import json
import time
import shutil
import tempfile
import uuid
import subprocess
from pathlib import Path

from backend.orchestration.state import RecoveryState
from backend.orchestration.runtime import recovery_runtime

async def run_benchmark_case(case_dir: Path):
    print(f"Running benchmark case: {case_dir.name}")
    
    # 1. Create a temp Git repository
    temp_dir = tempfile.mkdtemp(prefix=f"ag_bench_{case_dir.name}_")
    
    # Copy files
    for f in case_dir.iterdir():
        if f.is_file():
            shutil.copy2(f, temp_dir)
            
    # Init git repo
    subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "bench@test.com"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Bench Tester"], cwd=temp_dir, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=temp_dir, check=True, capture_output=True)
    
    incident_id = str(uuid.uuid4())
    
    # Run a failed pytest to get the stack trace
    res = subprocess.run(["pytest", "-q", "--disable-warnings", "--maxfail=1"], cwd=temp_dir, capture_output=True, text=True)
    stack_trace = res.stdout + "\n" + res.stderr
    
    state = {
        "incident_id": incident_id,
        "commit_sha": "bench0123",
        "repository_path": temp_dir,
        "repository_full_name": "demo/" + case_dir.name, # Dummy name to avoid real PR
        "stack_trace": stack_trace,
        "is_mock_mode": False,  # We want REAL LLM and real sandbox
        "telemetry": {},
        "retry_count": 0,
        "github_payload": {
            "repository": {"clone_url": temp_dir}
        },
        "current_patch_diff": "",
        "patch_explanation": "",
        "generated_test_code": "",
        "root_cause_analysis": {},
        "explainable_risk": {},
        "test_results": {},
        "human_decision": None
    }
    
    start_time = time.time()
    
    # To prevent PR creation, we can temporarily disable github token if it exists
    old_token = os.environ.get("GITHUB_TOKEN")
    if old_token:
        os.environ["GITHUB_TOKEN"] = "invalid_dummy_token"
        
    try:
        if recovery_runtime.graph is None:
            await recovery_runtime.start()
            
        final_state = await asyncio.wait_for(recovery_runtime.run(state), timeout=180.0)
    except asyncio.TimeoutError:
        print(f"Graph execution timed out for {case_dir.name}")
        final_state = state
    except Exception as e:
        print(f"Graph execution failed: {e}")
        final_state = state
    finally:
        if old_token:
            os.environ["GITHUB_TOKEN"] = old_token
            
    total_time = time.time() - start_time
    
    # Extract results
    fixed = final_state.get("test_results", {}).get("tests_passed", False)
    risk = final_state.get("explainable_risk", {})
    decision = risk.get("decision", "UNKNOWN")
    
    # Calculate tokens (approximation if not available directly in state)
    tokens = final_state.get("total_tokens", 0) # Might need to fetch from telemetry if injected
    # Assuming token tracking in nebius.py updates total_tokens in state, otherwise we set to 0
    
    retries = final_state.get("retry_count", 0)
    
    print(f"Result {case_dir.name}: fixed={fixed}, decision={decision}, time={total_time:.1f}s")
    
    # Clean up temp dir
    try:
        shutil.rmtree(temp_dir)
    except Exception:
        pass
        
    return {
        "case": case_dir.name,
        "fixed": fixed,
        "decision": decision,
        "total_time": round(total_time, 2),
        "tokens": tokens,
        "retries": retries,
        "error": None
    }
    
async def run_all(limit=None):
    results = []
    cases_dir = Path("benchmark/cases")
    if not cases_dir.exists():
        return
        
    cases = sorted([d for d in cases_dir.iterdir() if d.is_dir()])
    if limit:
        cases = cases[:int(limit)]
        
    for case in cases:
        try:
            res = await run_benchmark_case(case)
            results.append(res)
        except Exception as e:
            results.append({
                "case": case.name,
                "fixed": False,
                "decision": "ERROR",
                "error": str(e),
                "total_time": 0,
                "tokens": 0,
                "retries": 0
            })
            
    with open("benchmark/results.json", "w") as f:
        json.dump(results, f, indent=2)
        
    try:
        import subprocess
        subprocess.run(["python", "benchmark/report.py"])
    except Exception as e:
        print(f"Failed to generate report: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit number of cases")
    args = parser.parse_args()
    
    # Enforce constraints
    if "BENCHMARK_MAX_TOKENS" not in os.environ:
        os.environ["BENCHMARK_MAX_TOKENS"] = "100000"
        
    asyncio.run(run_all(args.limit))
