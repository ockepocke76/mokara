# Mokara — Port Plan (Phase 2)

**What:** The successor to `~/dev/mymontecarlo` (mokara.ai): the Monte Carlo
BTC/portfolio simulator rebuilt as **FastAPI + Next.js**, replacing the
Streamlit UI entirely.

**Why a fresh repo:** the old repo's history contains leaked secrets (Cloud
SQL password, RSA keys, a hardcoded admin password). This repo starts with
**zero secrets in history** — keep it that way (`.env` is gitignored from
commit one; `.env.example` documents required vars with placeholder values).

**Starting point:** the old repo's `pre-port-detangled` tag — phase 1 made
`core/`, `db/`, `services/`, `utils/`, `reporting/` and `background_tasks.py`
fully framework-free (zero streamlit imports, guardrail test enforces it).
Those packages are **copied** into `api/` here; the old repo is a read-only
reference from now on.

**Key context:** mokara.ai prod was torn down 2026-09-04 (zero running
infra). Nothing is live → no parity pressure, no strangler, no cutover. The
old Streamlit app runs locally as a behavioral reference only. Build by
value, ship when ready.

---

## Decisions

**Made:**
- Repo: `~/dev/mokara`, monorepo — `api/` (Python) + `web/` (Next.js)
- UI: Next.js App Router + TypeScript + **Tailwind + shadcn/ui**
- Auth: **Better Auth** in `web/` (Google login, same stack as linyfy);
  Next.js is the BFF — the browser only talks to Next, whose server-side
  route handlers call FastAPI internally with the authenticated user
  attached. FastAPI never handles browser auth.
- Charts: **react-plotly.js** in the browser, fed JSON series from the API
  (the precalculated percentile paths in regeneration packages map straight
  to responses). Matplotlib stays server-side for PDFs only.
- Content pages (About/Assets/Methodology/Glossary/Disclaimer) →
  **one `/docs` section** (MDX), content ported mostly verbatim.
- Admin → an **admin route group** in `web/` (kills the separate
  `admin_app.py` deployment).

- Hosting: **Cloud Run + Cloud SQL** (decided 2026-09-06) — the known
  stack; deploy scripts/knowledge from the old repo carry over. Prod DB can
  seed from the dump at `~/dev/mymontecarlo/backups/`. Still open within
  W7: worker as its own Cloud Run service vs. sidecar/same container.
- Tier/beta system: **port as-is** (decided 2026-09-06) — full
  `tier_config` + beta gating + AI credits come along in W1/W5.
- Branding: **rebrand as Mokara** (decided 2026-09-06) — product name is
  Mokara, domain mokara.ai. UI copy, page titles, PDF headers, and email
  addresses use Mokara; "MyMonteCarlo" survives only in engine internals
  until touched.

---

## Architecture

```
mokara/
├── api/                  # Python — FastAPI + the detangled engine
│   ├── app/              # FastAPI app: routers, deps, schemas (Pydantic)
│   ├── core/             # ← copied from pre-port-detangled
│   ├── db/               # ← copied (PostgreSQL-only)
│   ├── services/         # ← copied (job queue + worker)
│   ├── reporting/        # ← copied (PDF, plot-series builders)
│   ├── utils/            # ← copied
│   ├── worker.py         # background worker entrypoint (wraps services/background_worker)
│   ├── tests/            # ← copied suite + guardrail (streamlit ban → now a hard dep ban)
│   └── pyproject.toml
├── web/                  # Next.js App Router + TS + Tailwind + shadcn/ui
│   ├── app/
│   │   ├── (app)/        # dashboard, simulate, simulations, strategies, leaderboard, settings
│   │   ├── admin/        # admin route group (allowlist-gated)
│   │   ├── docs/         # MDX content section
│   │   └── api/          # Better Auth + BFF route handlers → FastAPI
│   └── ...
└── PORT_PLAN.md          # this file
```

**Job-first API** (phase 1's Wave 5 made this shape real — reuse it):
```
POST /simulations            → {job_id}         (BackgroundManager.start_simulation)
GET  /jobs/{id}              → status/progress   (poll_job_status)
GET  /simulations            → user's history + preview stats
GET  /simulations/{hash}     → regeneration package → chart series
POST /simulations/{hash}/pdf → {job_id}; GET …/pdf → download when ready
GET  /leaderboard, /community-stats, /beta-status
CRUD /strategies, POST /strategies/evaluate, POST /strategies/generate (Gemini)
GET  /config/params          → the config-driven parameter schema (drives the sim form)
Admin: /admin/users, /admin/jobs, /admin/migrations, …
```
Internal auth between Next and FastAPI: shared-secret header + user identity
claims (simple, both services in our control); revisit if the API is ever
exposed publicly.

**Explicitly NOT ported (dies with Streamlit):** cookies-manager + the
streamlit==1.50 pin, streamlit-authenticator/-oauth (vendored),
mobile_nav/device_detection hacks, `st.session_state` machinery
(`ui/session_state.py`), fragments/rerun polling, the Streamlit theme-sync
script, `admin_app.py` as a separate service.

---

## Waves

### W0 — Scaffold ✅ (2026-09-06)
- [x] Copy `core/ db/ services/ utils/ reporting/ background_tasks.py tests/`
      from `mymontecarlo@pre-port-detangled` into `api/`; make it a proper
      package with `pyproject.toml` (deps: the non-streamlit subset of the
      old requirements.txt).
- [x] Prune on copy: `background_tasks.py` UI-era wrappers we don't need,
      `config.yml` streamlit-theme keys, `tests/test_portfolio*.py` (broken
      stale imports — fix or drop).
- [x] Guardrail test evolves: forbid importing `streamlit` AND any UI-era
      leftovers in `api/` (streamlit isn't even installed → import test).
- [x] FastAPI skeleton: `/healthz`, DB ping, config loading (env-only via
      the phase-1 `core/secrets.py`).
- [x] `web/`: create-next-app (TS, App Router, Tailwind), shadcn/ui init,
      layout shell with nav.
- [x] CI (GitHub Actions): api pytest + web build/lint on PR.
- [x] `.env.example` for both halves; `.gitignore` correct from commit one.

### W1 — Auth ✅ (2026-09-06)
- [x] Better Auth in `web/` with Google provider; sessions in Postgres.
- [x] Link Better Auth users ↔ existing `USERS` table by email (keep the
      engine's user_id intact — job attribution, history, tiers all key on it).
- [x] Admin gate: tier-based, straight from the DB (`get_user_tier == 'ADMIN'`)
      — that's what old `ui/auth.is_admin` actually did; no allowlist file.
- [x] BFF plumbing: authenticated fetch helper (Next route handler →
      FastAPI with internal auth header + user claims).
- [x] Port the tier/beta system as-is: `tier_config`, beta gating
      (`get_beta_status` quota auto-approve), AI credits (`core/limits`).

Notes: GET /me on the API returns the full viewer profile (identity, beta
allowed-status w/ quota auto-approve, tier, admin flag, currency). Dev-only
email/password login (AUTH_DEV_LOGIN=1) makes every authed flow testable in
the browser without Google credentials; Google needs its redirect URI
(BETTER_AUTH_URL + /api/auth/callback/google) added in the Google console
before real logins work. Verified live: signup → session → BFF headers →
engine user auto-created (FREE tier, beta auto-approved).

### W2 — Read-only slice (proves API + charts end to end, cheaply)
- [ ] API: `/leaderboard`, `/community-stats`, `/beta-status`.
- [ ] Web: Leaderboard page + Dashboard (aggregates, radar/comparison
      charts via react-plotly).
- [ ] `/docs` MDX section: port the five content pages' text.

### W3 — Run Simulation (the core flow)
- [ ] API: `GET /config/params` exposing the config-driven parameter schema
      (the old sidebar generated sliders from config — same data drives a
      React form now); `POST /simulations` (validate via `validation.py`,
      queue job); `GET /jobs/{id}` with progress payload.
- [ ] Worker runs as a real process (`api/worker.py`); document the local
      run recipe (api + worker + web).
- [ ] Web: simulate page — param form (react-hook-form + zod from the
      schema), strategy picker, submit → progress (poll `/jobs/{id}`) →
      results charts from the regeneration package series.

### W4 — My Simulations + PDF
- [ ] API: history list w/ preview stats (the phase-1 `db/cache.py` wrappers
      become endpoint internals), simulation detail, delete (w/ the
      sim-limit confirm flow), PDF job + download.
- [ ] Web: simulations list with preview cards, detail view, PDF button
      with ready-state polling.

### W5 — Strategies (biggest single wave)
- [ ] API: strategies CRUD, `POST /strategies/generate` (Gemini,
      server-side, per-user AI-credit enforcement via `core/limits`),
      test-run endpoint, `POST /strategies/evaluate` (existing job type),
      evaluation results.
- [ ] Web: strategy list, designer (prompt → generated code → review →
      save), test, evolve, evaluation charts.
- [ ] Keep the RestrictedPython sandboxing exactly as the engine has it —
      custom strategy code is untrusted input.

### W6 — Settings + Admin
- [ ] Settings page: currency preference (UserProfileService).
- [ ] `admin/` route group: users + tiers, jobs table, leaderboard
      management, migrations trigger, danger zone (system reset — keep the
      DELETE-EVERYTHING + ADMIN_PASSWORD double confirm).

### W7 — Deploy (Cloud Run + Cloud SQL)
- [ ] Dockerfiles for api/worker/web; decide worker topology (own Cloud Run
      service vs. same container as api).
- [ ] Secrets as env vars in the host — never in the repo.
- [ ] Restore-from-backup path: prod DB dump lives at
      `~/dev/mymontecarlo/backups/` — decide whether new prod starts from
      it or fresh.
- [ ] Point mokara.ai; smoke test; announce.

---

## Working rules (carried from phase 1 — they worked)
- One wave per branch/commit-group; commit messages match the diff.
- Verify each wave against the local Streamlit app's behavior where
  applicable (it still runs, as reference).
- No secrets in commits, ever. `.env.example` only.
- Update this file's checkboxes + progress log as waves land.

## Progress log

| Date | Wave | Notes |
|------|------|-------|
| 2026-09-06 | — | Repo created; plan written. Decisions: mokara name, Tailwind+shadcn, docs consolidation. Open: hosting/DB, tier scope, branding. |
| 2026-09-06 | W0 | Scaffold complete: engine copied from tag (ui/layout→core/param_layout, ui/radar_chart_data→reporting, broken ui.formatting lazy import fixed, snowflake migrations + 4 UI tests + 2 stale tests pruned); pyarrow was a hidden streamlit transitive dep, now explicit. api: venv, 168 tests pass, FastAPI /healthz (db ping) + /internal/ping (BFF secret) verified live. web: create-next-app + shadcn (14 components), Mokara landing verified in browser, prod build clean. CI workflow (api pytest w/ PG service + migrations; web lint+build). |
| 2026-09-06 | W1 | Auth complete: Better Auth (PG tables migrated) + Google provider (env-gated) + dev credentials login; BFF apiFetch/getViewer with internal secret + identity headers; API /me (5 new tests); site header w/ session + user menu; login page. Full loop verified in browser. |
| 2026-09-06 | — | Remaining decisions closed: Cloud Run + Cloud SQL, tier system ported as-is, full rebrand to Mokara. All decisions made — W0 is unblocked. |
