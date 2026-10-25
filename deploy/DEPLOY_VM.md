# VM Deployment Guide: Autonomous Recovery Engine (ARE)

Production deployment instructions for hosting the ARE backend on a Linux VM (Ubuntu/Debian) behind a Caddy reverse proxy with automatic TLS.

---

## 1. Prerequisites
- A Linux VM with at least 2 vCPU, 4GB RAM (Ubuntu 22.04/24.04 recommended)
- A public DNS A-record pointing to your VM's public IP (e.g. `api.yourdomain.com`)
- Docker Engine & Docker Compose (`docker compose version`)
- Caddy web server (`sudo apt install -y caddy`)

---

## 2. Server Setup & Repository Clone
```bash
git clone https://github.com/Sahil707-pop/autonomous-recovery-engine.git /opt/aegiscore
cd /opt/aegiscore

# Copy production environment template
cp deploy/.env.prod.example .env

# Edit .env with your real API keys, credentials, and domains
nano .env
```

---

## 3. Start Backend Services
```bash
# Launch PostgreSQL and the ARE backend
docker compose -f docker-compose.prod.yml up -d --build backend postgres

# Verify service health
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend
```
The backend will bind securely to `127.0.0.1:8000`.

---

## 4. Configure Caddy (Reverse Proxy + Auto-TLS)
```bash
# Copy Caddyfile configuration
sudo cp deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile # Update with your domain

# Format and reload Caddy (provisions Let's Encrypt certificate automatically)
sudo caddy fmt --overwrite /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

Verify public endpoint health:
```bash
curl -s https://api.yourdomain.com/health | jq .
```

---

## 5. Netlify Frontend Configuration
1. Open your Netlify Site Dashboard -> **Site configuration** -> **Environment variables**.
2. Add:
   - `NEXT_PUBLIC_API_BASE_URL`: `https://api.yourdomain.com`
3. Trigger a new deploy in Netlify.

---

## 6. GitHub OAuth & Webhook Registration
- **GitHub OAuth App**:
  - Application name: `Autonomous Recovery Engine`
  - Homepage URL: `https://your-site.netlify.app`
  - Authorization callback URL: `https://api.yourdomain.com/auth/github/callback`
- **GitHub Repository Webhook**:
  - Payload URL: `https://api.yourdomain.com/webhook/github`
  - Content type: `application/json`
  - Secret: matches `GITHUB_WEBHOOK_SECRET` in `.env`
  - Events: `Workflow runs` and `Pull requests`
