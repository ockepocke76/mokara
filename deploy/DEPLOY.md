# Mokara — Cloud Run deployment runbook (W7)

Stack: **Cloud Run + Cloud SQL (PostgreSQL) + GCS + Secret Manager**
(decided 2026-09-06). Nothing is live yet — mokara.ai's old infra was torn
down 2026-09-04, so this is a from-scratch bring-up, not a cutover.

## Topology

```
browser ──HTTPS──▶ mokara-web (Next.js BFF, public)
                        │  INTERNAL_API_SECRET header
                        ▼
                   mokara-api (FastAPI, request/response only)
                        │ enqueue job rows          ▲ read results / PDF bytes
                        ▼                           │
                   Cloud SQL (BACKGROUND_JOBS + all state)      GCS (PDFs)
                        ▲                                        ▲
                        │ FOR UPDATE SKIP LOCKED                 │ save_pdf
                   mokara-worker (same image as api, `python worker.py`)
```

**Worker topology decision (was the open W7 question):** the worker runs as
its **own Cloud Run service**, not a sidecar in the api container (the old
Streamlit `start.sh` pattern). Reasons:

- Cloud Run throttles CPU outside HTTP requests; a sidecar worker would
  starve mid-job whenever the api is idle. A separate service runs with
  `--no-cpu-throttling` + `min-instances=1` and never throttles.
- Independent sizing: sims + 45-page matplotlib PDFs want 2 CPU / 2 GiB;
  the api stays at 1 CPU / 1 GiB and can scale to zero.
- Independent scaling under load: raise the worker's `max-instances` —
  the job queue's `FOR UPDATE SKIP LOCKED` makes N concurrent workers safe.
  (Cloud Run won't autoscale it on queue depth; scaling is manual or a
  later Cloud Monitoring automation.)
- Cloud Run services must listen on `$PORT`; `worker.py` starts a stdlib
  health listener when `PORT` is set (no FastAPI in the worker).

## 1. Prerequisites

- `gcloud` authenticated with owner/editor on the target project.
- A GCP project (default `mokara-prod` — override `MOKARA_PROJECT_ID`).
- A Google OAuth client (web) with redirect URI
  `https://mokara.ai/api/auth/callback/google`; note client id + secret.
- A Gemini API key. New keys can't call `gemini-2.5-pro` — set
  `GEMINI_MODEL_STRONG` to a 3.x model on the api/worker services if needed.

## 2. One-time infra

Export the secret values (see the header of `setup-infra.sh` — generated
locally, pushed to Secret Manager, never committed), then:

```bash
./deploy/setup-infra.sh
```

Creates: Artifact Registry repo, `mokara-run` service account + IAM,
Cloud SQL instance `mokara-db` (POSTGRES_17, db-g1-small, nightly backups)
with database `btc_simulator_prod` / user `app_user`, bucket
`<project>-pdfs`, and all secrets.

## 3. Database: seed or fresh? **(DECISION NEEDED — Oscar)**

A prod dump exists at `~/dev/mymontecarlo/backups/`. Options:

- **A. Restore the dump** — keeps old users, simulation history,
  leaderboard, community stats. PDFs referenced by old rows are gone with
  the old bucket (regenerate on demand; `pdf_status` should be reset).
- **B. Start fresh** — clean launch, run migrations only. Old users
  re-register; leaderboard/community stats start empty.

Either way, after restore-or-create run the migrations through the Cloud
SQL Auth Proxy from a local shell:

```bash
cloud-sql-proxy mokara-prod:europe-west4:mokara-db --port 5433 &
cd api && POSTGRES_HOST=localhost POSTGRES_PORT=5433 POSTGRES_DB=btc_simulator_prod \
  POSTGRES_USER=app_user POSTGRES_PASSWORD=… .venv/bin/python run_migrations.py
cd ../web && DATABASE_URL=postgresql://app_user:…@localhost:5433/btc_simulator_prod \
  npx @better-auth/cli@latest migrate -y --config lib/auth.ts
```

## 4. Deploy

```bash
export GOOGLE_CLIENT_ID=…        # web needs it as plain env
./deploy/deploy.sh all           # or api | worker | web
```

Images build in Cloud Build (no local Docker), tagged with the git SHA.
`api` and `worker` share one image; the worker overrides the command.

## 5. Domain

```bash
gcloud run domain-mappings create --service mokara-web --domain mokara.ai --region europe-west4
```

Point DNS per the command's output. `BETTER_AUTH_URL` already assumes
`https://mokara.ai` (config.sh `PUBLIC_URL`).

## 6. Smoke test

1. `curl https://<api-url>/healthz` → ok + DB ping.
2. mokara.ai loads; Google login round-trips.
3. Run a small simulation (S&P 500 bootstrap, 30y × 1000) → progress bar
   advances → charts render (proves web→api→queue→worker→DB chain).
4. Request the PDF → status flips pending→ready → download works
   (proves worker→GCS→api→BFF chain).
5. Leaderboard + community stats render.
6. Admin section reachable for the promoted admin user only.

## 7. Rollback

Cloud Run keeps prior revisions:

```bash
gcloud run services update-traffic mokara-web --to-revisions <rev>=100 --region europe-west4
```

DB: nightly automated backups on the instance; restore via
`gcloud sql backups restore`.

## Follow-ups (accepted, not blockers)

- **api hardening**: the api is HTTPS-reachable but every endpoint requires
  the internal secret header. Tighten later with IAM service-to-service
  auth (ID tokens from web, `--no-allow-unauthenticated`) or
  `--ingress internal` + Direct VPC egress on web.
- **Worker autoscaling on queue depth** (manual `max-instances` for now).
- CI/CD: deploys are manual `deploy.sh` runs for now; a GitHub Actions
  deploy on main can come later.
