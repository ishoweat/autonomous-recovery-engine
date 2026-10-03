import os
import json
import fnmatch

def get_critical_path_score(file_path: str) -> float | None:
    """
    Returns the file criticality score if the file_path matches any 
    glob pattern defined in the CRITICAL_PATHS_JSON environment variable.
    Format of env var: '{"auth/**": 0.5, "payments/**": 0.6}'
    Returns None if no match.
    """
    rules_env = os.environ.get("CRITICAL_PATHS_JSON")
    if not rules_env:
        return None
        
    try:
        rules: dict[str, float] = json.loads(rules_env)
    except json.JSONDecodeError:
        return None
        
    highest_score = None
    for pattern, score in rules.items():
        if fnmatch.fnmatch(file_path, pattern) or fnmatch.fnmatch(file_path, f"*/{pattern}"):
            if highest_score is None or score > highest_score:
                highest_score = score
                
    return highest_score
