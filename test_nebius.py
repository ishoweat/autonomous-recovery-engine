import os
import requests

api_key = os.environ.get("NEBIUS_API_KEY", "")
if not api_key:
    print("No NEBIUS_API_KEY set")
    exit(1)

resp = requests.get("https://api.tokenfactory.nebius.com/v1/models", headers={"Authorization": f"Bearer {api_key}"})
if resp.status_code == 200:
    models = resp.json().get("data", [])
    for m in models:
        print(m.get("id"))
else:
    print(resp.status_code, resp.text)
