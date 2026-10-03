# Feedback: Nebius Token Factory & NVIDIA Models

During our development of Antigravity, we heavily relied on the **Nebius Token Factory** and NVIDIA's **Nemotron** models. Here is our constructive feedback based on real integration experiences.

## 1. NVIDIA Nemotron-3.5-Lightning / Ultra
- **Reasoning Quality vs Latency**: The Lightning tier was fantastic for our triage phase. We observed rapid response times (often under 0.8s) which is critical for an autonomous agent making split-second decisions on whether to act on a webhook. For complex root-cause analysis involving multi-file diffs and stack traces, we successfully scaled up to the Ultra models which provided much deeper context synthesis.
- **Context Windows**: The context limits were generally sufficient, but when ingesting large tracebacks or massive unified diffs, we had to heavily sanitize and chunk the inputs to avoid hitting token ceilings.
- **Empty Output on Over-Thinking**: A major observed quirk was that if the model's "thinking" phase consumed the entire token budget, it would sometimes return an empty content block. We solved this by enforcing stricter system prompts requesting structured JSON outputs early in the generation process and increasing `max_tokens`.

## 2. Nebius Token Factory Platform
- **Model Discovery**: Discovering available models programmatically was slightly obtuse until we realized we could use the standard OpenAI-compatible `/v1/models` endpoint. Having a more prominent dashboard listing exact string identifiers (`nvidia/Nemotron-3_5-Lightning`, etc.) would speed up initial configuration.
- **Latency and Throughput**: We were highly impressed with the throughput. The real-time inference telemetries recorded during our benchmark runs confirmed that the API maintains stable low latency even when parallelizing background graph nodes.
- **OpenAI Compatibility**: The strict adherence to the OpenAI client standard was a huge win. We were able to plug the Nebius API directly into our existing LangChain/LangGraph infrastructure by simply swapping the base URL and API key.

## Conclusion
The combination of Nebius serverless scaling and NVIDIA's Nemotron reasoning models was the perfect backbone for our Autonomous Reliability Engine. It gave us the speed needed for real-time CI/CD hooks and the reasoning depth required to actually fix code.
