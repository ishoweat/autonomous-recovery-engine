import re

with open("backend/llm/nebius.py", "r") as f:
    content = f.read()

replacement = """
                    est_cost = None
                    if token_usage:
                        from backend.config import get_settings
                        settings = get_settings()
                        if model_used == settings.active_fast_model and settings.price_per_mtok_fast is not None:
                            est_cost = (token_usage["total_tokens"] / 1_000_000) * settings.price_per_mtok_fast
                        elif model_used == settings.active_strong_model and settings.price_per_mtok_strong is not None:
                            est_cost = (token_usage["total_tokens"] / 1_000_000) * settings.price_per_mtok_strong
                        
                    self.last_telemetry = {
                        "provider": "Nebius Token Factory",
                        "model": model_used,
                        "request_started": req_started,
                        "response_received": req_finished,
                        "success": True,
                        "status_code": 200,
                        "finish_reason": finish_reason,
                        "latency": latency,
                        "token_usage": token_usage,
                        "est_cost": est_cost,
                        "inference_status": "RECEIVED",
                    }
"""

content = re.sub(
    r'self\.last_telemetry = \{\n\s+"provider": "Nebius Token Factory",\n\s+"model": model_used.*?\}',
    replacement.strip(),
    content,
    flags=re.DOTALL
)

replacement2 = """
                    est_cost = None
                    if token_usage:
                        from backend.config import get_settings
                        settings = get_settings()
                        m_used = getattr(response, "model", create_kwargs["model"]) or create_kwargs["model"]
                        if m_used == settings.active_fast_model and settings.price_per_mtok_fast is not None:
                            est_cost = (token_usage["total_tokens"] / 1_000_000) * settings.price_per_mtok_fast
                        elif m_used == settings.active_strong_model and settings.price_per_mtok_strong is not None:
                            est_cost = (token_usage["total_tokens"] / 1_000_000) * settings.price_per_mtok_strong
                        
                    self.last_telemetry = {
                        "provider": "Nebius Token Factory",
                        "model": m_used,
                        "request_started": req_started,
                        "response_received": req_finished,
                        "success": True,
                        "status_code": 200,
                        "finish_reason": finish_reason,
                        "latency": latency,
                        "request_id": getattr(response, "id", None),
                        "token_usage": token_usage,
                        "est_cost": est_cost,
                        "inference_status": "RECEIVED",
                    }
"""

content = re.sub(
    r'self\.last_telemetry = \{\n\s+"provider": "Nebius Token Factory",\n\s+"model": getattr\(response, "model".*?\}',
    replacement2.strip(),
    content,
    flags=re.DOTALL
)

with open("backend/llm/nebius.py", "w") as f:
    f.write(content)
