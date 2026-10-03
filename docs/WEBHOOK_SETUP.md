# Webhook Setup Guide

To enable fully autonomous mode, you need to route GitHub webhooks to this service.

## 1. Expose a Public URL
Use a service like `ngrok` to expose your local port (e.g., `8000`):
```bash
ngrok http 8000
```
This will give you a public URL like `https://abcdef.ngrok.app`.

## 2. Configure GitHub Webhook
1. Go to your target repository on GitHub.
2. Navigate to **Settings** > **Webhooks** > **Add webhook**.
3. **Payload URL**: `https://<YOUR_NGROK_URL>/api/webhooks/github`
4. **Content type**: Select `application/json`
5. **Secret**: Generate a strong secret. Set it here and save it as `GITHUB_WEBHOOK_SECRET` in your `.env`.
6. **Events**: Select **Let me select individual events.** and check:
   - Workflow runs
   - Pull requests
7. Save the webhook.

## 3. Enable Webhook Ingress
Make sure `ENABLE_WEBHOOK_INGRESS=true` is set in your `.env`.

## 4. How to Test
1. Make a breaking commit in your repository to trigger the CI workflow.
2. The GitHub Action will fail, and a `workflow_run` event with `conclusion: failure` will be sent.
3. The Autonomous Recovery Engine will verify the payload signature, fetch the failed logs, and automatically launch a recovery incident.
4. You can also run `python scripts/send_test_webhook.py` locally to simulate events.

## 5. Rotating the Secret
If you ever suspect your secret is compromised:
1. Generate a new secret.
2. Update the webhook setting on GitHub.
3. Update `GITHUB_WEBHOOK_SECRET` in your `.env` and restart the backend.
