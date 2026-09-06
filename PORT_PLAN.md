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

### W2 — Read-only slice ✅ (2026-09-06)
- [x] API: `/leaderboard` (+`/leaderboard/meta` for category/profile selectors, profile-score fallback like the old UI), `/community-stats`, `/beta-status`. 5 tests.
- [x] Web: Leaderboard page (table w/ medals, category+profile filters via URL params) + Dashboard (stat cards, most-run-strategies Plotly bar w/ empty state, getting-started links). `components/chart.tsx` = SSR-safe react-plotly wrapper on plotly.js-dist-min.
- [x] `/docs` MDX section (@next/mdx + typography plugin): methodology/glossary/disclaimer GENERATED verbatim from `reporting/content.py` via script; about (Mokara story) + assets hand-ported. Sidebar layout.

### W3 — Run Simulation ✅ (2026-09-06)
- [x] API: `GET /config/params` — strategies (class param defs + BBD
      conditional-visibility rules), assets (per-model params incl.
      num_years), sections (tax exposed under the engine's `tax_method`
      key); `POST /simulations` — faithful port of _start_simulation
      (beta + AI-credit gates, currency from profile, validate → 422,
      hash/cache/history, stale-cache replacement rerun; responses:
      cached | running | queued); `GET /jobs/{id}` with progress payload;
      `GET /simulations/{hash}/results` — stats + chart series (percentile
      fan, Net-Worth slice of the MultiIndex sampled_paths, histogram,
      median yearly table, AI content).
- [x] Worker runs as a real process (`api/worker.py` →
      services/background_worker.run_worker).
- [x] Web: simulate page — schema-driven form (plain state, ParamField
      renders slider+input/select/checkbox with percent scaling and
      visible_if; form is noValidate — engine validation is authoritative,
      config defaults can sit off native step grids), submit → BFF →
      poll → results page: stat cards, log-scale percentile fan with
      sampled paths, outcome histogram, median yearly table, AI analysis
      (hidden when disabled). Verified END TO END in the browser: real
      S&P 500 bootstrap 30y × 1000 runs through form → worker → charts.

### W4 — My Simulations + PDF ✅ (2026-09-06)
- [x] API: `GET /simulations` (history + preview stats via the phase-1
      cache wrappers, description strings), `DELETE /simulations/{hash}`
      (ownership-checked, clears caches), `POST /simulations/{hash}/pdf`
      (queues job), `GET …/pdf/status` (engine vocabulary:
      pending→ready|failed), `GET …/pdf` (bytes from pdf_storage,
      ownership-checked). 4 tests (182 total).
- [x] Web: /simulations list — cards with description, success/median
      badges, View / PDF (generate→poll→download) / Delete (confirm
      dialog); BFF routes incl. PDF byte streaming. Detail view = W3's
      results page. Verified in browser; real 45-page PDF generated by the
      worker and downloaded through the full chain.

### W5 — Strategies: agentic generation ✅ built (2026-09-06) — awaiting review/merge + live-key validation

**Design settled 2026-09-06** (discussion w/ Claude in linyfy session). The
old one-shot Gemini prompt is NOT ported. Generation becomes a **LangGraph
workflow**; create and evolve are ONE graph (evolve = same graph with an
optional `seed_strategy` input). Deps: `langgraph` +
`langgraph-checkpoint-postgres` ONLY — no langchain model/chain layer; nodes
are plain Python calling `call_gemini_safe` / google-genai directly.

```
extract_spec → (clarify?) → retrieve → plan → generate → validate ──fail──┐
     ↑ interrupt (only if ambiguous,      (pseudocode,     │ ok            │
       max 1 round, skippable)            self-checked     static_review   │
                                          vs spec)         │ ok            │
                                                        test_sim + paired │
                                                        baseline (same    │
                                                        seeds)            │
                                                           │              │
                                                        analyze ──spec────┘
                                                           │    mismatch
                                                           │ conforms      (rework,
                                                       review interrupt     ≤ cap)
                                                       (user: save /
                                                        change → loop /
                                                        discard)
                                                           │
                                                         save
```

**Graph state (Pydantic):** user_request, seed_strategy (nullable → evolve),
spec (structured: category, risk posture, mechanics, constraints, proposed
params), clarifications, retrieved examples, plan, code+description,
validation results per rung, sim stats + baseline delta, analyze verdict,
attempt count, credit usage. Checkpointed in Postgres → interrupt/resume
across HTTP requests by thread_id.

**Nodes → existing engine functions:**
- `extract_spec` / `clarify`: cheap model; clarify fires ONLY when the spec
  has holes (conditional interrupt), one round, "proceed with assumptions"
  always offered.
- `retrieve`: the 3 built-ins' `get_user_prompt_template()` (prompt→code
  few-shot pairs) + SQL top-N validated public strategies by evaluation
  score filtered by category + a "common mistakes" negative-example block
  (seed from `tests/ai_strategy_snippets/*_fail` patterns: in-place `+=`,
  dunders, missing `evaluation_category`). No embeddings/RAG.
- `generate`: strong model; plan-then-code; explicit parameter-design step
  (names/defaults/ranges). API-surface text derived from
  `inspect.getdoc(BaseStrategy)` — kill the hand-duplicated blocks.
- `validate`: `execute_strategy_code` (RestrictedPython, unchanged —
  custom strategy code stays untrusted input) + dry run.
- `static_review`: fast LLM pass — "does the code implement the spec?"
  Catches wrong-logic-that-compiles before spending a sim.
- `test_sim`: `run_sandbox_test` + a category-matched baseline built-in on
  the SAME seeds (paired comparison; 10 unpaired paths is noise).
- `analyze`: judges **spec-conformance ONLY** (see Goodhart rule below),
  using summary_stats + per-year traces; produces the plain-language
  explanation ("in a typical year it does X; in a crash Y") → saved as
  `ai_description`.
- `rework`: targeted repair prompt scoped to the failed rung with only the
  relevant evidence; hard iteration cap.
- `save`: `save_custom_strategy` + git branch (existing GitHubService flow).

**Hard rules:**
- **Goodhart guardrail:** the rework loop triggers on spec *mismatch* only.
  Faithful-but-underperforming results go to the USER at review ("does what
  you asked; underperforms baseline — adjust?") — never silent rework
  toward better stats (that's overfitting to 10 paths).
- **Credits:** metered per RUN (one generation = one price), internal LLM
  calls capped by budget, enforced via `core/limits`. Fixes the old bug —
  generation was accidentally unmetered (only sim analysis was).
- Analyze/explain copy stays descriptive, never advisory ("the strategy
  withdrew X in scenario Y", not "you should…") — simulation code, not
  investment advice.

Checklist (built on branch `feature/w5-agentic-strategies`, worktree
`.claude/worktrees/w5-agentic` — NOT merged; see progress log):
- [x] Engine prep: seed param on `run_sandbox_test` (paired baseline);
      `_validate_strategy_class` checks `evaluation_category()`;
      per-year traces flow to the graph via yearly_results;
      prompt API-docs from `inspect.getdoc` (`core/strategy_docs.py`).
- [x] Graph: `api/app/agents/` (graph/runner/prompts/retrieval/llm) —
      nodes+edges per the diagram above, Postgres checkpointer on the
      engine DB, 3-attempt + 3-revision caps, 14-call LLM budget.
      LLM injected per-call; `MOKARA_FAKE_LLM=1` = canned provider (tests
      + keyless dev e2e). Tiers: fast/strong via GEMINI_MODEL_FAST/_STRONG
      (defaults gemini-2.5-flash / gemini-2.5-pro).
- [x] Trace logging from day one: V36 migration —
      `STRATEGY_GENERATION_RUNS` + `_EVENTS` (append-only build log; UI
      rehydrates from it, SSE tails it).
- [x] API: strategies CRUD (soft delete); `POST /strategies/generate`
      (per-RUN credit metering up front) → {run_id}; run-state GET; SSE
      events tail w/ reconnect cursor; resume (clarify/review); test-run
      endpoint; evaluate via existing job type + evaluation GET.
- [x] Web: strategy list w/ active-run banners; designer per
      **W5_DESIGNER_UX.md**; detail page (params, code, test flight,
      evolve, evaluate, delete); evolve = designer seeded via
      `?seed=<id>`.
- [x] Tiered models per node — env-configured, fake provider for dev.

Open after W5 (small): live validation with a real GEMINI_API_KEY (none on
this machine — canned provider verified the full flow end-to-end in the
browser instead); evolve code shown as full block, not a diff view;
pre-run credit count on the Generate button (429 is handled, count isn't
shown); evaluation charts on the detail page (evaluate queues + leaderboard
shows results, per-strategy chart panel not built).

Fast-follow (post-W5, not blocking): dedupe → offer clone when spec matches
a built-in/public strategy; behavioral assertions (spec → mechanical checks
on per-year traces); dead-parameter detection (perturb-and-rerun).
**Deliberately NOT now:** embeddings/RAG, N parallel candidates, in-loop
8-scenario evaluation, parameter auto-tuning.

### W6 — Settings + Admin ✅ (2026-09-06)
- [x] Settings page: currency preference via `PUT /me/settings`
      (validated against get_currency_options; UserProfileService).
- [x] `admin/` route group (layout 404s non-admins; API re-checks tier on
      every endpoint; Admin item in user menu for admins):
      **Users** — unified registered+pre-authorized table (SQL ported from
      old admin_app.get_unified_user_data), per-row tier select
      (update_user_tier w/ SUBSCRIPTION_HISTORY audit), allow/revoke,
      pre-authorize form. **Jobs** — background-jobs table w/ status badges.
      **System** — run migrations, re-run all leaderboard evaluations
      (builtin + custom, same job payloads as old admin), danger zone with
      the DELETE-EVERYTHING + ADMIN_PASSWORD double confirm.
      BFF: catch-all /api/bff/admin/[...path] proxy. 5 API tests (187
      total). Browser-verified as an ADMIN user (dev@mokara.local promoted
      locally); reset button NOT clicked.

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
| 2026-09-06 | W2 | Read-only slice done; all three pages verified in browser against live local DB. Gotcha fixed: uvicorn launch config now uses --reload (stale server had 404'd new routers). |
| 2026-09-06 | W3 | Core flow complete + browser-verified e2e. Found: engine config oddity (return_threshold_rate default 0 < min 0.5 — surfaced by native form validation, now bypassed; engine validates server-side). 178 api tests green. |
| 2026-09-06 | W4 | My Simulations + PDF done, browser-verified; 45-page PDF through worker→storage→API→BFF. Engine pdf_status vocabulary is lowercase pending/ready/failed. STOPPED HERE per Oscar: W5 on hold for agentic-flow redesign; W6+W7 not started. |
| 2026-09-06 | W6 | Settings + Admin done, browser-verified. Only W5 (agentic designer, design settled) and W7 (deploy — needs Oscar's go for billing) remain. |
| 2026-09-06 | — | Remaining decisions closed: Cloud Run + Cloud SQL, tier system ported as-is, full rebrand to Mokara. All decisions made — W0 is unblocked. |
| 2026-09-06 | W5 | Hold lifted: agentic-generation design settled and written into the W5 section (LangGraph, one graph for create+evolve, validation ladder w/ paired baseline, spec-conformance-only rework, per-run credit metering). Implementation not started. |
| 2026-09-06 | W5 | BUILT on `feature/w5-agentic-strategies` (worktree, 5 commits: engine prep → DB → graph → API → web). 204 api tests green (+2 skipped) incl. graph/API e2e on the canned LLM; full designer flow browser-verified (create→clarify→review→save, refine, discard, rehydration banner, detail test-flight w/ chart). NOT merged — awaits Oscar's review + explicit merge go-ahead. No Gemini key on this machine: live-LLM run still unvalidated; set GEMINI_API_KEY and unset MOKARA_FAKE_LLM to go live. deps: langgraph 1.2.11 + checkpoint-postgres 3.1.2. |
