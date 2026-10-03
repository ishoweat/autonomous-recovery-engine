from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI, APIConnectionError, APIStatusError, APITimeoutError

from backend.config import get_settings


import logging

logger = logging.getLogger(__name__)


class NebiusLLMError(RuntimeError):
    """Raised when Nebius inference fails."""


_LLM_CACHE: dict[str, str] = {}

class NebiusNemotron:
    """Async OpenAI-compatible client for Nebius Token Factory."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
    ) -> None:
        if not api_key:
            raise ValueError(
                "NEBIUS_API_KEY must be configured for real LLM execution."
            )

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout_seconds,
            max_retries=2,
        )
        self.last_telemetry: dict[str, Any] = {}


    async def complete(
        self,
        *,
        system_prompt: str,
        model: str | None = None,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        stream_to_incident_id: str | None = None,
    ) -> str:
        """Generate a recovery-agent response and record structured telemetry."""
        from datetime import datetime, timezone
        import time
        from backend.orchestration.telemetry import emit_node_event

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

        base_kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                },
            ],
            "temperature": (
                self.temperature
                if temperature is None
                else temperature
            ),
            "max_tokens": (
                self.max_tokens
                if max_tokens is None
                else max_tokens
            ),
        }
        if response_format is not None:
            base_kwargs["response_format"] = response_format

        max_attempts = 2
        for attempt in range(max_attempts):
            create_kwargs = dict(base_kwargs)
            if attempt == 1:
                logger.warning("Retrying Nebius call with enable_thinking=False due to empty content.")
                create_kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}

            if stream_to_incident_id:
                create_kwargs["stream"] = True
                create_kwargs["stream_options"] = {"include_usage": True}

            try:
                response = await self.client.chat.completions.create(**create_kwargs)

                if stream_to_incident_id:
                    content = ""
                    token_usage = None
                    finish_reason = None
                    model_used = create_kwargs["model"]

                    async for chunk in response:
                        if chunk.choices:
                            delta = getattr(chunk.choices[0].delta, "content", None)
                            if not delta:
                                delta = getattr(chunk.choices[0].delta, "reasoning_content", None)

                            if delta:
                                content += delta
                                await emit_node_event(
                                    incident_id=stream_to_incident_id,
                                    event_type="llm_token_chunk",
                                    node_name="llm_stream",
                                    message="Streaming chunk",
                                    metadata={"chunk": delta}
                                )
                            finish_reason = getattr(chunk.choices[0], "finish_reason", finish_reason)
                        
                        if hasattr(chunk, "usage") and chunk.usage:
                            token_usage = {
                                "prompt_tokens": getattr(chunk.usage, "prompt_tokens", 0),
                                "completion_tokens": getattr(chunk.usage, "completion_tokens", 0),
                                "total_tokens": getattr(chunk.usage, "total_tokens", 0),
                            }
                        
                        if hasattr(chunk, "model") and chunk.model:
                            model_used = chunk.model
                    
                    if not content or not str(content).strip():
                        if attempt == 0:
                            continue # retry
                        else:
                            raise NebiusLLMError("Nebius returned empty completion in stream.")
                    
                    latency = round(time.perf_counter() - t0, 3)
                    req_finished = datetime.now(timezone.utc).isoformat()
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
                    if settings.enable_llm_cache and cache_key:
                        _LLM_CACHE[cache_key] = str(content).strip()
                    return str(content).strip()
                else:
                    # Non-stream
                    latency = round(time.perf_counter() - t0, 3)
                    req_finished = datetime.now(timezone.utc).isoformat()

                    choice = response.choices[0] if response.choices else None
                    finish_reason = getattr(choice, "finish_reason", None) if choice else None

                    token_usage = None
                    if hasattr(response, "usage") and response.usage:
                        token_usage = {
                            "prompt_tokens": getattr(response.usage, "prompt_tokens", 0),
                            "completion_tokens": getattr(response.usage, "completion_tokens", 0),
                            "total_tokens": getattr(response.usage, "total_tokens", 0),
                        }

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

                    if not response.choices:
                        raise NebiusLLMError("Nebius returned no completion choices.")

                    msg = response.choices[0].message
                    content = getattr(msg, "content", None)

                    if not content and hasattr(msg, "reasoning_content") and msg.reasoning_content:
                        content = msg.reasoning_content
                    elif not content and hasattr(msg, "reasoning") and msg.reasoning:
                        content = msg.reasoning

                    if not content or not str(content).strip():
                        if attempt == 0:
                            continue # try again with enable_thinking=False
                        else:
                            raise NebiusLLMError(f"Nebius returned an empty completion (finish_reason: {finish_reason}).")

                    logger.info("Nebius LLM completion success")
                    final_res = str(content).strip()
                    if settings.enable_llm_cache and cache_key:
                        _LLM_CACHE[cache_key] = final_res
                    return final_res

            except APITimeoutError as exc:
                latency = round(time.perf_counter() - t0, 3)
                self.last_telemetry = {
                    "provider": "Nebius Token Factory",
                    "model": create_kwargs["model"],
                    "request_started": req_started,
                    "response_received": datetime.now(timezone.utc).isoformat(),
                    "success": False,
                    "status_code": None,
                    "latency": latency,
                    "inference_status": "ERROR",
                    "error": "Nebius Token Factory request timed out.",
                }
                raise NebiusLLMError("Nebius Token Factory request timed out.") from exc
            except APIConnectionError as exc:
                latency = round(time.perf_counter() - t0, 3)
                self.last_telemetry = {
                    "provider": "Nebius Token Factory",
                    "model": create_kwargs["model"],
                    "request_started": req_started,
                    "response_received": datetime.now(timezone.utc).isoformat(),
                    "success": False,
                    "status_code": None,
                    "latency": latency,
                    "inference_status": "ERROR",
                    "error": "Unable to connect to Nebius Token Factory.",
                }
                raise NebiusLLMError("Unable to connect to Nebius Token Factory.") from exc
            except APIStatusError as exc:
                if response_format is not None and exc.status_code == 400 and attempt == 0:
                    base_kwargs["response_format"] = None
                    continue # Will retry without response format since we modify base_kwargs. But wait, base_kwargs won't be copied again for attempt=1 if we do it here. Let's just do a recursive call like before.
                    
                # Recursive retry logic for 400 Bad Request
                if response_format is not None and exc.status_code == 400:
                    logger.warning("Nebius LLM returned 400 Bad Request with response_format=%s. Retrying without response_format.", response_format)
                    return await self.complete(
                        system_prompt=system_prompt,
                        model=model,
                        user_prompt=user_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        response_format=None,
                        stream_to_incident_id=stream_to_incident_id,
                    )

                latency = round(time.perf_counter() - t0, 3)
                self.last_telemetry = {
                    "provider": "Nebius Token Factory",
                    "model": create_kwargs["model"],
                    "request_started": req_started,
                    "response_received": datetime.now(timezone.utc).isoformat(),
                    "success": False,
                    "status_code": exc.status_code,
                    "latency": latency,
                    "inference_status": "ERROR",
                    "error": f"Nebius Token Factory returned HTTP {exc.status_code}: {exc.message}",
                }
                raise NebiusLLMError(f"Nebius Token Factory returned HTTP {exc.status_code}: {exc.message}") from exc


    async def complete_json(
        self,
        *,
        system_prompt: str,
        model: str | None = None,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream_to_incident_id: str | None = None,
    ) -> dict[str, Any]:
        """Request and parse a JSON object from Nemotron using OpenAI structured JSON output."""

        # Enforce JSON instruction in system prompt if not present
        effective_system = system_prompt
        if "json" not in effective_system.lower():
            effective_system = f"{effective_system}\n\nIMPORTANT: Respond with a valid JSON object only."

        content = await self.complete(
            system_prompt=effective_system,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
            response_format={"type": "json_object"},
            stream_to_incident_id=stream_to_incident_id,
        )

        cleaned = content.strip()
        import re

        # Strip chain-of-thought blocks if present (e.g. <think>...</think> or <thought>...</thought>)
        cleaned = re.sub(r"<(?:thought|think)>[\s\S]*?</(?:thought|think)>", "", cleaned).strip()

        # Strip any plain-text thinking preamble that appears before the JSON object.
        # Models like Claude Sonnet (Thinking) may emit prose before the first `{`.
        first_brace = cleaned.find("{")
        if first_brace > 0:
            cleaned = cleaned[first_brace:]

        def try_parse(candidate: str) -> dict[str, Any] | None:
            c = candidate.strip()
            if not c:
                return None

            def parse_text(text: str) -> dict[str, Any] | None:
                # 1. Standard json.loads
                try:
                    p = json.loads(text, strict=False)
                    if isinstance(p, dict):
                        return p
                except Exception:
                    pass

                # 2. Trailing comma fix
                try:
                    no_trailing = re.sub(r",\s*([\]}])", r"\1", text)
                    p = json.loads(no_trailing, strict=False)
                    if isinstance(p, dict):
                        return p
                except Exception:
                    pass

                # 3. Python boolean/None conversion (True -> true, False -> false, None -> null)
                try:
                    python_fixed = re.sub(r"\bTrue\b", "true", text)
                    python_fixed = re.sub(r"\bFalse\b", "false", python_fixed)
                    python_fixed = re.sub(r"\bNone\b", "null", python_fixed)
                    python_fixed = re.sub(r",\s*([\]}])", r"\1", python_fixed)
                    p = json.loads(python_fixed, strict=False)
                    if isinstance(p, dict):
                        return p
                except Exception:
                    pass

                # 4. Try ast.literal_eval for Python dict literals
                try:
                    import ast
                    val = ast.literal_eval(text)
                    if isinstance(val, dict):
                        return val
                except Exception:
                    pass

                return None

            suffixes = ["", "\"", "\"}", "\"\n}", "}", "}]}", "\"}]}"]
            for suffix in suffixes:
                res = parse_text(c + suffix)
                if res is not None:
                    return res
            return None

        # 1. Try direct parsing
        res = try_parse(cleaned)
        if res is not None:
            return res

        # 2. Extract from markdown code fences ```json ... ``` or ``` ... ```
        code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        for block in reversed(code_blocks):
            res = try_parse(block)
            if res is not None:
                return res

        # 3. Iterate candidates across all brace pairs (from outermost inward)
        brace_indices = [m.start() for m in re.finditer(r"\{", cleaned)]
        rbrace_indices = [m.start() for m in re.finditer(r"\}", cleaned)]

        for start in brace_indices:
            for end in reversed(rbrace_indices):
                if end > start:
                    res = try_parse(cleaned[start : end + 1])
                    if res is not None:
                        return res

        raise NebiusLLMError(
            f"Nemotron returned invalid JSON. Response snippet: {cleaned[:120]}"
        )

    async def close(self) -> None:
        await self.client.close()


def create_nebius_client() -> NebiusNemotron:
    """Create the configured Nemotron client."""

    settings = get_settings()

    return NebiusNemotron(
        api_key=settings.nebius_api_key,
        base_url=settings.nebius_base_url,
        model=settings.active_nemotron_model,
        temperature=settings.nebius_temperature,
        max_tokens=settings.nebius_max_tokens,
        timeout_seconds=settings.nebius_timeout_seconds,
    )


def create_nebius_fast_client() -> NebiusNemotron:
    """Create the configured fast Nemotron client."""

    settings = get_settings()

    return NebiusNemotron(
        api_key=settings.nebius_api_key,
        base_url=settings.nebius_base_url,
        model=settings.active_fast_model,
        temperature=settings.nebius_temperature,
        max_tokens=settings.nebius_max_tokens,
        timeout_seconds=settings.nebius_timeout_seconds,
    )


def create_nebius_strong_client() -> NebiusNemotron:
    """Create the configured strong Nemotron client."""

    settings = get_settings()

    return NebiusNemotron(
        api_key=settings.nebius_api_key,
        base_url=settings.nebius_base_url,
        model=settings.active_strong_model,
        temperature=settings.nebius_temperature,
        max_tokens=settings.nebius_max_tokens,
        timeout_seconds=settings.nebius_timeout_seconds,
    )
