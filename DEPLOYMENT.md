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

- **Web**: `https://doclens.jayprajapati.dev` → Caddy serves `/srv/web/doclens`
- **API**: `https://doclens-api.jayprajapati.dev` → Caddy → `doclens-backend:8001`
- **Brain**: DocLens reaches it in-cluster at `http://brain-backend:8000` (also public at
  `https://brain.jayprajapati.dev`). Brain owns Qdrant + embeddings — DocLens can't serve without it.
- **State**: DocLens owns its data in the shared **mongo** (`doclens` db + user). Vectors live in the
  shared **qdrant** (collection `doclens`, created lazily by Brain on first ingest).
- Backend image is built by CI (GitHub Actions → GHCR); the server only **pulls**. It never compiles.

BYOK: only `/chat` needs a provider key; it's forwarded per-request and never stored server-side.

---

# Everyday deploys

| You changed… | Deploy |
|---|---|
| Backend code / API (`backend/**`) | **Backend** (§1) |
| Backend + a new env var/secret | **Backend + env** (§2) |
| Frontend (`frontend/**`) | **Frontend web** (§3) |
| Brain (RAG engine) | Deploy **Brain** from its own repo (`~/Brain/DEPLOY.md`) |
| A feature spanning both | Ship **backend first**, then frontend |

## §1. Backend — code change (no new env)

1. Merge to `main`. CI (`publish-backend-image.yml`) builds and pushes a new image to GHCR.
2. Deploy it — **either** GitHub → Actions → **Deploy Backend** → Run workflow, **or** on the server:
   ```bash
   cd /srv/doclens
   docker compose pull
   docker compose up -d          # recreates the container on the new image
   docker compose logs -f backend
   ```
3. Verify: `curl -s https://doclens-api.jayprajapati.dev/health`

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

## §3. Frontend web (`doclens.jayprajapati.dev`)

Static export served by Caddy — no container:
```bash
cd frontend
npm run build                                             # produces frontend/dist/
rsync -az --delete dist/ deploy@<server-ip>:/srv/web/doclens/
```
Live immediately. Ensure the build's `VITE_API_BASE_URL` is
`https://doclens-api.jayprajapati.dev` (set in `frontend/.env.prod`).

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
Point `doclens.jayprajapati.dev` and `doclens-api.jayprajapati.dev` (A records) at the server IP.
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
curl https://brain.jayprajapati.dev/health
curl https://doclens-api.jayprajapati.dev/health
# then open https://doclens.jayprajapati.dev, add a BYOK key, upload a doc, ask a question.
```
