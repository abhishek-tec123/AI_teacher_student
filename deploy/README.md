# AI Teacher — Production Deployment

## Architecture

```
User
  |
  v
Frontend (https://tecorb.in)
  |
  v
Nginx (443, SSL)
  |
  v
FastAPI / Uvicorn (127.0.0.1:3018, 4 workers)
  |
  +-- MongoDB Atlas
  +-- Redis
```

## Server Details

- **Host:** `ec2-13-233-214-195.ap-south-1.compute.amazonaws.com`
- **OS:** Ubuntu 24.04 LTS
- **Project dir:** `/home/ubuntu/AI_Teacher`
- **Virtualenv:** `.venv`
- **Service:** `AITEACHER`
- **Domain:** `https://api.tecorb.in`
- **SSL:** Let's Encrypt / Certbot

## One-Command Deploy

From your local repo root (on `feat/in-progress`):

```bash
./deploy/deploy.sh
```

This rsyncs code, installs dependencies, copies the systemd service, and restarts.

## Manual systemd Commands

```bash
# Status
sudo systemctl status AITEACHER

# Restart
sudo systemctl restart AITEACHER

# Logs
sudo journalctl -u AITEACHER -f

# View recent logs
sudo journalctl -u AITEACHER -n 100 --no-pager
```

## Nginx

Config file on server:
```bash
/etc/nginx/sites-available/api
```

Test and reload:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

## SSL Renewal

Test auto-renewal:
```bash
sudo certbot renew --dry-run
```

## Environment / Secrets

`.env` is **never** copied by the deploy script. Manage it manually on the server:

```bash
nano /home/ubuntu/AI_Teacher/.env
sudo systemctl restart AITEACHER
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 502 Bad Gateway | FastAPI not running | `sudo systemctl restart AITEACHER` |
| CORS error | Wrong `CORS_ORIGINS` in `.env` | Edit `.env`, restart |
| SSL error | Cert expired | `sudo certbot renew` |
| High disk usage | Old logs / cache | Clean manually (apt, journalctl, pip cache) |
| ImportError on deploy | `src/` layout mismatch | Ensure service uses `src.main:app` |
