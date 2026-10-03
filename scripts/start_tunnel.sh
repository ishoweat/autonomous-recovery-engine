#!/usr/bin/env bash

set -Eeuo pipefail

BACKEND_PORT="${BACKEND_PORT:-8000}"
TUNNEL_PROVIDER="${TUNNEL_PROVIDER:-cloudflare}"
TUNNEL_HOSTNAME="${TUNNEL_HOSTNAME:-}"
NGROK_DOMAIN="${NGROK_DOMAIN:-}"

WEBHOOK_PATH="/webhook/github"

cleanup() {
    echo
    echo "[tunnel] shutting down"
}

trap cleanup EXIT INT TERM

if ! curl \
    --silent \
    --show-error \
    --fail \
    "http://127.0.0.1:${BACKEND_PORT}/health" \
    >/dev/null; then

    echo "[tunnel] backend is not reachable on port ${BACKEND_PORT}"
    exit 1
fi

echo "[tunnel] backend is healthy"
echo "[tunnel] webhook target: ${WEBHOOK_PATH}"

case "${TUNNEL_PROVIDER}" in

    smee)
        WEBHOOK_PROXY_URL="${WEBHOOK_PROXY_URL:-${SMEE_URL:-}}"
        if [[ -z "${WEBHOOK_PROXY_URL}" ]]; then
            echo "[tunnel] WEBHOOK_PROXY_URL or SMEE_URL is required for smee provider (e.g. https://smee.io/your-channel)"
            exit 1
        fi
        echo "[tunnel] starting Smee webhook forwarder"
        echo "[tunnel] public proxy: ${WEBHOOK_PROXY_URL}"
        echo "[tunnel] forwarding to: http://127.0.0.1:${BACKEND_PORT}${WEBHOOK_PATH}"
        exec npx -y smee-client \
            --url "${WEBHOOK_PROXY_URL}" \
            --target "http://127.0.0.1:${BACKEND_PORT}${WEBHOOK_PATH}"
        ;;

    gh)
        if ! command -v gh >/dev/null 2>&1; then
            echo "GitHub CLI (gh) is required"
            exit 1
        fi
        GITHUB_REPO="${GITHUB_REPO:-}"
        if [[ -z "${GITHUB_REPO}" ]]; then
            echo "[tunnel] GITHUB_REPO is required (e.g. owner/repo)"
            exit 1
        fi
        echo "[tunnel] starting GitHub CLI webhook forwarder for ${GITHUB_REPO}"
        echo "[tunnel] forwarding to: http://127.0.0.1:${BACKEND_PORT}${WEBHOOK_PATH}"
        exec gh webhook forward \
            --repo="${GITHUB_REPO}" \
            --events="workflow_run" \
            --url="http://127.0.0.1:${BACKEND_PORT}${WEBHOOK_PATH}"
        ;;

    cloudflare)
        if ! command -v cloudflared >/dev/null 2>&1; then
            echo "cloudflared is required"
            exit 1
        fi

        if [[ -n "${TUNNEL_HOSTNAME}" ]]; then
            echo "[tunnel] starting Cloudflare named tunnel"
            echo "[tunnel] public webhook:"
            echo "https://${TUNNEL_HOSTNAME}${WEBHOOK_PATH}"

            exec cloudflared tunnel \
                --url "http://127.0.0.1:${BACKEND_PORT}" \
                --hostname "${TUNNEL_HOSTNAME}"
        fi

        echo "[tunnel] starting Cloudflare quick tunnel"
        exec cloudflared tunnel \
            --url "http://127.0.0.1:${BACKEND_PORT}"
        ;;

    ngrok)
        if ! command -v ngrok >/dev/null 2>&1; then
            echo "ngrok is required"
            exit 1
        fi

        echo "[tunnel] starting ngrok"

        if [[ -n "${NGROK_DOMAIN}" ]]; then
            echo "[tunnel] webhook:"
            echo "https://${NGROK_DOMAIN}${WEBHOOK_PATH}"

            exec ngrok http \
                --domain="${NGROK_DOMAIN}" \
                "${BACKEND_PORT}"
        fi

        exec ngrok http "${BACKEND_PORT}"
        ;;

    *)
        echo "Unsupported TUNNEL_PROVIDER: ${TUNNEL_PROVIDER}"
        echo "Use: smee, gh, cloudflare, or ngrok"
        exit 1
        ;;
esac
