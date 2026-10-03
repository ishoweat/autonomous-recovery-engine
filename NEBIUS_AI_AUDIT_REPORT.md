# Nebius AI & NVIDIA Nemotron Audit

## Quick Answers

* **Is Nebius AI Token Factory being used right now?**  
  **NO.** The backend has the code ready, but it is not active.

* **Is NVIDIA Nemotron doing live model inference?**  
  **NO.** No real AI model calls are succeeding.

* **Is the integration real and authenticated?**  
  **NO, NOT AUTHENTICATED.** The API key in `.env` is just placeholder text (`your_nebius_api_key`). Whenever the app tries to connect, Nebius rejects it with error `401 Unauthorized`.

---

## Where the Code Lives & What It Actually Does

### 1. The Main AI Client
* **File:** `backend/llm/nebius.py`
* **What it does:** This is the connector that talks to `https://api.tokenfactory.nebius.com/v1/` using model `nvidia/nemotron-4-340b-instruct`.
* **Current status:** Fails because the API key is not real.

### 2. "Analyse & Fix" Button in the Web UI
* **Route:** `POST /api/remediate`
* **File:** `backend/api/remediate.py`
* **Current status:** **Does not call any AI model.** Although the UI log says *"Nemotron-70B analysing error"*, it actually uses built-in Python pattern rules (`_smart_fix`) to patch the code.

### 3. Automated Bug Fixing Pipeline (LangGraph)
* **Route:** `POST /api/v1/incident/{id}/approve`
* **File:** `backend/orchestration/nodes.py`
* **Current status:** Tries to call Nebius for triage, root-cause analysis, and code repair. Because the key is invalid, it catches the 401 error and falls back to offline rule-based diagnosis.

### 4. Advanced Checks & Polyglot Fixes
* **Routes:** `POST /api/v2/adversarial/check` and `POST /api/v2/polyglot/fix`
* **File:** `backend/api/v2.py`
* **Current status:** Detects that there is no real API key and returns pre-set mock responses.

### 5. Plain English Error Explanations
* **Route:** `POST /api/v1/incident/{id}/explain-failure`
* **File:** `backend/api/incidents.py`
* **Current status:** Falls back to hardcoded explanation templates whenever Nebius returns 401.

---

## Summary

The project is completely coded and ready to use Nebius and Nemotron, but **it is running 100% offline using built-in fallback rules** because it does not have a real API key.

To enable real AI responses, add a valid Nebius key to `.env`:
```bash
NEBIUS_API_KEY=your_real_key_here
```
