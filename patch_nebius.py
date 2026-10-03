import re

with open("backend/llm/nebius.py", "r") as f:
    content = f.read()

# Add cache dictionary at the top
if "_LLM_CACHE: dict[str, str] = {}" not in content:
    content = content.replace("class NebiusNemotron:", "_LLM_CACHE: dict[str, str] = {}\n\nclass NebiusNemotron:")

cache_logic = """
        req_started_dt = datetime.now(timezone.utc)
        req_started = req_started_dt.isoformat()
        t0 = time.perf_counter()

        from backend.config import get_settings
        settings = get_settings()

        cache_key = None
        if settings.enable_llm_cache:
            import hashlib
            hasher = hashlib.sha256()
            hasher.update(system_prompt.encode("utf-8"))
            hasher.update(user_prompt.encode("utf-8"))
            cache_key = hasher.hexdigest()
            if cache_key in _LLM_CACHE:
                logger.info(f"LLM Cache HIT for key {cache_key}")
                self.last_telemetry = {
                    "provider": "Nebius Token Factory (Cache)",
                    "model": model or self.model,
                    "request_started": req_started,
                    "response_received": datetime.now(timezone.utc).isoformat(),
                    "success": True,
                    "status_code": 200,
                    "finish_reason": "stop",
                    "latency": 0.01,
                    "token_usage": None,
                    "est_cost": 0.0,
                    "inference_status": "RECEIVED",
                }
                return _LLM_CACHE[cache_key]
"""

content = re.sub(
    r'        req_started_dt = datetime.now\(timezone.utc\)\n        req_started = req_started_dt.isoformat\(\)\n        t0 = time.perf_counter\(\)',
    cache_logic.strip(),
    content,
    count=1
)

cache_save_stream = """
                    if settings.enable_llm_cache and cache_key:
                        _LLM_CACHE[cache_key] = str(content).strip()
                    return str(content).strip()
"""
content = re.sub(
    r'                    return str\(content\).strip\(\)\n\s+else:\n\s+# Non-stream',
    cache_save_stream.strip() + "\n                else:\n                    # Non-stream",
    content,
    count=1
)

cache_save_non_stream = """
                    logger.info("Nebius LLM completion success")
                    final_res = str(content).strip()
                    if settings.enable_llm_cache and cache_key:
                        _LLM_CACHE[cache_key] = final_res
                    return final_res
"""
content = re.sub(
    r'                    logger.info\("Nebius LLM completion success"\)\n\s+return str\(content\).strip\(\)',
    cache_save_non_stream.strip(),
    content,
    count=1
)

with open("backend/llm/nebius.py", "w") as f:
    f.write(content)
