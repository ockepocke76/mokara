# Mokara

Monte Carlo BTC/portfolio simulator — successor to the Streamlit-based
`mymontecarlo` (mokara.ai), rebuilt as FastAPI + Next.js.

- **[CLAUDE.md](CLAUDE.md)** — workflow rules (branching, review, merge policy, definition of done). Read before contributing.
- **[PORT_PLAN.md](PORT_PLAN.md)** — architecture, decisions, and the wave-by-wave build tracker. Start here.
- **[PARITY_REPORT.md](PARITY_REPORT.md)** — Streamlit-parity status and accepted differences.
- `api/` — FastAPI + the simulation engine (copied from `mymontecarlo@pre-port-detangled`)
- `web/` — Next.js App Router + TypeScript + Tailwind + shadcn/ui + Better Auth

## Running locally

Prereqs: local PostgreSQL with the `btc_simulator_local` database (Homebrew
PG, current-user auth), Node 20+, Python 3.12+.

One-time setup:

```bash
cd api && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
cp api/.env.example api/.env    # fill in: INTERNAL_API_SECRET (openssl rand -hex 32), POSTGRES_USER
cd web && npm install
cp web/.env.example web/.env    # fill in: same INTERNAL_API_SECRET, BETTER_AUTH_SECRET, DATABASE_URL, AUTH_DEV_LOGIN=1
cd api && .venv/bin/python run_migrations.py
cd web && npx @better-auth/cli@latest migrate -y --config lib/auth.ts
```

Then three processes (three terminals):

```bash
cd api && .venv/bin/uvicorn app.main:app --port 8000 --reload
```

```bash
cd api && .venv/bin/python worker.py
```

```bash
cd web && npm run dev -- -p 3100
```

Open http://localhost:3100. With `AUTH_DEV_LOGIN=1` in `web/.env` you can
create a local account with email+password (no Google credentials needed).
Google login additionally requires `GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`
and the redirect URI `<BETTER_AUTH_URL>/api/auth/callback/google` registered
in the Google console.

To use the admin section, promote your user in the local DB:

```bash
cd api && .venv/bin/python -c "from db.database import db; db.update_user_tier(db.get_or_create_user_id('you@example.com',''), 'ADMIN', changed_by='local-setup', reason='dev admin')"
```

Tests: `cd api && .venv/bin/python -m pytest tests/` (needs the local DB) and
`cd web && npm run lint && npm run build`.

## Deployment

Cloud Run + Cloud SQL. See **[deploy/DEPLOY.md](deploy/DEPLOY.md)** for the
topology, one-time infra setup (`deploy/setup-infra.sh`), and the deploy
script (`deploy/deploy.sh`). Nothing is live yet.

## Ground rule

This repo was started fresh so its history contains **no secrets** — the old
repo's history is burned (leaked DB password, RSA keys). Configuration comes
from environment variables only; commit `.env.example` updates, never `.env`.
