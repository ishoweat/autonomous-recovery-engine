import json
import hmac
import hashlib
import requests
import os
import sys

def send_webhook(event_type, payload, delivery_id):
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "test-secret")
    url = "http://localhost:8000/api/webhooks/github"
    
    body = json.dumps(payload).encode("utf-8")
    
    signature = "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    
    headers = {
        "X-Hub-Signature-256": signature,
        "X-GitHub-Event": event_type,
        "X-GitHub-Delivery": delivery_id,
        "Content-Type": "application/json",
        "Content-Length": str(len(body))
    }
    
    try:
        resp = requests.post(url, data=body, headers=headers)
        print(f"[{event_type}] Status Code: {resp.status_code}")
        print(f"[{event_type}] Response: {resp.text}")
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to {url}. Is the server running?")
        sys.exit(1)

def main():
    import sys
    
    mode = "workflow_run"
    if len(sys.argv) > 1 and sys.argv[1] == "--pr":
        mode = "pull_request"

    if mode == "workflow_run":
        payload = {
            "action": "completed",
        "workflow_run": {
            "name": "CI Tests",
            "conclusion": "failure",
            "id": 123456,
            "html_url": "https://github.com/demo/autonomous-recovery-engine/actions/runs/123456",
            "head_sha": "0123456789abcdef",
            "head_branch": "main"
        },
        "repository": {
            "name": "autonomous-recovery-engine",
            "full_name": "demo/autonomous-recovery-engine",
            "html_url": "https://github.com/demo/autonomous-recovery-engine",
            "owner": {
                "login": "demo"
            }
        }
        }
        send_webhook("workflow_run", payload, "test-delivery-id-001")
        
    elif mode == "pull_request":
        payload = {
            "action": "closed",
            "pull_request": {
                "number": 42,
                "merged": True,
                "merge_commit_sha": "0123456789abcdef",
                "html_url": "https://github.com/demo/autonomous-recovery-engine/pull/42",
            },
            "repository": {
                "name": "autonomous-recovery-engine",
                "full_name": "demo/autonomous-recovery-engine",
                "html_url": "https://github.com/demo/autonomous-recovery-engine",
                "owner": {
                    "login": "demo"
                }
            }
        }
        send_webhook("pull_request", payload, "test-delivery-id-002")

if __name__ == "__main__":
    main()
