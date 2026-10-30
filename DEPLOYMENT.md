# Deployment

How DocLens is deployed on the Hetzner shared-infra box, and how to ship changes
from now on. One source of truth.

## What's running

```
Hetzner server
 ├─ /srv/infra        shared stack (one per server): caddy (TLS) + postgres + redis + mongo + qdrant
 ├─ /srv/brain        brain-backend container (RAG engine; joins web + data networks)
 ├─ /srv/doclens      doclens-backend container (joins web + data networks)
 └─ /srv/web/doclens  static Vite build served by caddy
```

- **Web**: `https://doclens.jayyprajapati.com` → Caddy serves `/srv/web/doclens`
- **API**: `https://doclens-api.jayyprajapati.com` → Caddy → `doclens-backend:8001`
- **Brain**: DocLens reaches it in-cluster at `http://brain-backend:8000` (no public route). Brain owns
  Qdrant + embeddings — DocLens can't serve without it.
- **State**: DocLens owns its data in the shared **mongo** (`doclens` db + user). Vectors live in the
  shared **qdrant** (collection `doclens`, created lazily by Brain on first ingest).
- Backend image is built by CI (GitHub Actions → GHCR); the server only **pulls**. It never compiles.

Two chat modes: **free** (server's own Ollama key `HOSTED_OLLAMA_API_KEY`; model, quotas and on/off are
set in Admin → DocLens → Settings) and **BYOK** (user's key, forwarded per request, never stored).
Live settings and usage analytics are managed from the Admin panel (see "Admin control" below).

---

# Launch release (Oct 2026) — one-time steps, in this order

This release moves upload parsing into a sandbox inside DocLens, adds signed sessions, free mode, the
admin control/analytics API, and needs a Brain release. **Do every step; skipping 2 or 3 takes the
site down (sessions) or exposes the admin API.**

1. **Deploy Brain first** (`~/Brain/DEPLOY.md`). Its changes are additive and safe for Portfolio:
   CPU-bound handlers run in the threadpool (a big upload no longer stalls other apps), input caps
   (`max_ingest_chars`), `reasoning` on `/v1/generate`, `chunk_index` on retrieve.
2. **New secrets** in `/srv/doclens/backend.env` (template: `backend.env.example`):
   ```bash
   echo "SESSION_SECRET=$(openssl rand -hex 32)"  >> /srv/doclens/backend.env
   TOKEN=$(openssl rand -hex 32); echo "ADMIN_API_TOKEN=$TOKEN" >> /srv/doclens/backend.env
   echo "HOSTED_OLLAMA_API_KEY=<your ollama.com key>" >> /srv/doclens/backend.env
   # Admin side, same token:
   printf "DOCLENS_API_URL=http://doclens-backend:8001\nDOCLENS_ADMIN_TOKEN=$TOKEN\n" >> /srv/admin/backend.env
   ```
   Also set `CORS_ALLOWED_ORIGINS=https://doclens.jayyprajapati.com`.
3. **Caddy** — block the internal API publicly and cap request bodies. Replace the `doclens-api` block
   in `/srv/infra/Caddyfile` with:
   ```caddy
   doclens-api.jayyprajapati.com {
   	@internal path /internal/*
   	respond @internal 404
   	request_body {
   		max_size 30MB
   	}
   	reverse_proxy doclens-backend:8001
   }
   ```
   then `cd /srv/infra && docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile`.
4. **Copy the new compose file** (it adds containment: 1 CPU, 900 MB, read-only root, no capabilities):
   `cp <repo>/docker-compose.yml /srv/doclens/` → `cd /srv/doclens && docker compose pull && docker compose up -d`.
5. **Frontend** (§3) right after the backend — the new backend only accepts signed sessions; the new
   frontend upgrades every existing browser to one (same user id, their docs survive).
6. **Admin**: deploy the Admin backend + frontend, then register the DocLens sections:
   `cd /srv/admin && docker compose up -d && docker compose exec backend node scripts/ensure-doclens-project.js`.
7. **Turn free mode on** in Admin → DocLens → Settings: pick the model (**Test** it first), check the
   quotas, set the launch banner, Save. Free mode stays off until you do this.
8. **Verify**:
   ```bash
   curl -s https://doclens-api.jayyprajapati.com/health                          # {"status":"ok"}
   curl -s -o /dev/null -w "%{http_code}\n" https://doclens-api.jayyprajapati.com/internal/admin/config   # 404
   curl -s -X POST https://doclens-api.jayyprajapati.com/session -H 'Content-Type: application/json' -d '{}'   # {"token":"dl1...."}
   docker stats --no-stream doclens-backend                                     # MEM LIMIT 900MiB
   ```
   Then open the site in a private window: free mode selected, upload a PDF, ask a question, and watch it
   appear in Admin → DocLens → Activity.

**Recommended for the box** (not required): it has <1 GB free RAM and no swap (Brain alone is ~3.4 GB).
A 4 GB swap file (`fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile`
+ fstab) turns a memory spike anywhere into slowness instead of the OOM-killer picking a container.

## Admin control (no redeploys)

Admin → DocLens has **Overview** (users, questions, latency, grounded/blocked rates, documents chunked /
rejected / deleted, daily chart), **Activity** (every question + answer + timings + guardrail flags,
uploads, rejections, deletions, per-user view) and **Settings** (kill switches, banner, free-mode model +
fallback + quotas, BYOK providers/models, answer depth, verifier, retrieval thresholds, upload limits,
document expiry). Settings live in Mongo (`doclens_settings`) and apply within ~10 s.

What stays in env on purpose (a deploy to change): secrets, and the hard ceilings that protect the shared
server (`EXTRACT_*`, `HARD_MAX_*`) — the admin panel can tune limits only underneath them.

# Everyday deploys

| You changed… | Deploy |
|---|---|
| Backend code / API (`backend/**`) | **Backend** (§1) |
| Backend + a new env var/secret | **Backend + env** (§2) |
| Frontend (`frontend/**`) | **Frontend web** (§3) |
| Brain (RAG engine) | Deploy **Brain** from its own repo (`~/Brain/DEPLOY.md`) |
| A feature spanning both | Ship **backend first**, then frontend |

> **Before deploying a change to prompts / retrieval / guardrails:** `cd backend && python -m pytest tests -q`
> and, with Brain + Mongo running locally, `python evals/run_eval.py ... && python evals/compare.py <last-good> <new>`
> (see `EVALS.md`). The new settings in `backend.env.example` are optional; the image has no new dependencies.
> This release also relies on two *additive* Brain changes (`reasoning` on `/v1/generate`, `chunk_index` on
> retrieved chunks). DocLens works against an older Brain (it just ignores `reasoning`), but deploy Brain first.

## §1. Backend — code change (no new env)

1. Merge to `main`. CI (`publish-backend-image.yml`) builds and pushes a new image to GHCR.
2. Deploy it — **either** GitHub → Actions → **Deploy Backend** → Run workflow, **or** on the server:
   ```bash
   cd /srv/doclens
   docker compose pull
   docker compose up -d          # recreates the container on the new image
   docker compose logs -f backend
   ```
3. Verify: `curl -s https://doclens-api.jayyprajapati.com/health`

## §2. Backend — change that needs a new env var / secret

1. Add it in three places: the code that reads it (`backend/app/config.py`), `backend.env.example`
   (placeholder + comment), and the server's live `/srv/doclens/backend.env` (the real value).
2. On the server:
   ```bash
   nano /srv/doclens/backend.env
   cd /srv/doclens
   docker compose pull            # if code also changed; skip if only env changed
   docker compose up -d           # re-reads backend.env by recreating the container
   ```
   A plain `restart` does **not** pick up env changes — use `up -d`.

## §3. Frontend web (`doclens.jayyprajapati.com`)

Static export served by Caddy — no container:
```bash
cd frontend
npm run build                                             # produces frontend/dist/
rsync -az --delete dist/ deploy@<server-ip>:/srv/web/doclens/
```
Live immediately. Ensure the build's `VITE_API_BASE_URL` is
`https://doclens-api.jayyprajapati.com` (set in `frontend/.env.prod`).

## Rollback

- **Backend**: images are tagged by commit SHA. On the server, pin the previous one in
  `/srv/doclens/docker-compose.yml` (`image: ...doclens-backend:<old-sha>`) then `docker compose up -d`.
- **Web**: re-`rsync` the previous `dist/`.

---

# First-time onboarding (new server / disaster recovery)

All commands on the server as `deploy`. Assumes the shared infra stack (`/srv/infra`) exists — if not,
stand it up first from the Settl repo's `deploy/infra/` + `DEPLOYMENT.md` (it now includes mongo + qdrant).

### 1. Ensure mongo + qdrant are running in shared infra
If the infra predates them, refresh and bring them up:
```bash
cd ~/Settl && git pull
cp deploy/infra/docker-compose.yml deploy/infra/Caddyfile deploy/infra/infra.env.example /srv/infra/
nano /srv/infra/infra.env      # add MONGO_INITDB_ROOT_USERNAME/PASSWORD (openssl rand -base64 32)
cd /srv/infra && docker compose up -d
```

### 2. Create DocLens's Mongo database + user
```bash
DOCLENS_DB_PW=$(openssl rand -base64 32); echo "SAVE: $DOCLENS_DB_PW"
ROOT_PW=$(grep MONGO_INITDB_ROOT_PASSWORD /srv/infra/infra.env | cut -d= -f2-)
docker exec -i mongo mongosh -u root -p "$ROOT_PW" --authenticationDatabase admin <<EOF
db.getSiblingDB('doclens').createUser({
  user: 'doclens',
  pwd: '${DOCLENS_DB_PW}',
  roles: [{ role: 'readWrite', db: 'doclens' }]
})
EOF
```

### 3. Caddy routes
`/srv/infra/Caddyfile` already includes the `doclens-api` + `doclens` (static) blocks (from the Settl
infra template). If missing, add them and reload:
```bash
cd /srv/infra && docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile
```

### 4. DNS
Point `doclens.jayyprajapati.com` and `doclens-api.jayyprajapati.com` (A records) at the server IP.
On Cloudflare set them **DNS only (grey cloud)** so Caddy can obtain certs.

### 5. Deploy the backend container
```bash
sudo mkdir -p /srv/doclens && sudo chown deploy:deploy /srv/doclens
cp ~/DocLens/docker-compose.yml /srv/doclens/
cp ~/DocLens/backend.env.example /srv/doclens/backend.env && chmod 600 /srv/doclens/backend.env
nano /srv/doclens/backend.env      # MONGO_URI password=$DOCLENS_DB_PW, BRAIN_API_KEY (== Brain's)
cd /srv/doclens
docker login ghcr.io -u jayyprajapati   # once, PAT with read:packages
docker compose pull && docker compose up -d
```
Make sure Brain is deployed too (`~/Brain/DEPLOY.md`).

### 6. Deploy the frontend
```bash
cd ~/DocLens/frontend && npm ci && npm run build
rsync -az --delete dist/ deploy@<server-ip>:/srv/web/doclens/   # or run rsync from your laptop
```

### 7. CI secrets
In the GitHub repo (Settings → Secrets and variables → Actions) add `DEPLOY_HOST`, `DEPLOY_USER`
(=`deploy`), `DEPLOY_SSH_KEY` (a private key whose public half is in the server's
`/home/deploy/.ssh/authorized_keys`).

### Smoke test
```bash
curl https://doclens-api.jayyprajapati.com/health
# then open https://doclens.jayyprajapati.com, add a BYOK key, upload a doc, ask a question.
```
