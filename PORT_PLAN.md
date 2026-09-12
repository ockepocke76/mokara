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

### W5 — Strategies: agentic generation ✅ MERGED to main (2026-09-08) — live-key validation still pending

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

Open after W5 (small): ~~live validation with a real GEMINI_API_KEY~~ DONE
2026-09-10: key added to api/.env, full designer flow run live end-to-end
(spec → blueprint → code → checks → paired test flight → review → save →
full evaluation via worker, Excellence 45.13). Gotcha: new API keys can't
call gemini-2.5-pro (404 "no longer available to new users") — strong tier
overridden via GEMINI_MODEL_STRONG=gemini-3.1-pro-preview (documented in
.env.example); fast tier gemini-2.5-flash still works.
Still open: evolve code shown as full block, not a diff view;
pre-run credit count on the Generate button (429 is handled, count isn't
shown). ~~Evaluation charts on the detail page~~ DONE 2026-09-12: the
strategy-detail-tabs extension added an Evaluation tab (score + radar +
component grid + scenario table, in-progress polling) — see progress log.

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

### WV — Visual identity & page-by-page parity (added 2026-09-06, runs before W7)

The functional port works but reads as a generic monochrome shadcn app; the
old Streamlit app had a real brand. Grounded in a side-by-side session
against the live old app (bypass_login temporarily enabled, since reverted).

**The old app's design language (what "professional" meant):**
- Palette: **orange `#FF6B35`** primary (CTAs, sliders, active states),
  **navy `#2E4057`** headings/text, white bg + `#F4F6F8` secondary surfaces,
  soft-blue info banners, soft-yellow warning banners.
- **Brand header on every page**: logo mark (`ui/assets/mokara_logo.png` in
  the old repo — copy it over) + "mokara.ai" wordmark + tagline
  *"Wisdom of the Crowd, Applied"*. Footer: "© 2026 Mokara.AI · Stockholm,
  Sweden 🇸🇪 · Made with ❤️ and ☕ for better financial futures".
- **Voice**: emoji-led page titles (🚀 Run Simulation, 🏆 Strategy
  Leaderboard), pedagogic info boxes (the "Wisdom of the Crowd" explainer,
  ISK-tax caveat), a dismissible ✨ Early Access banner.
- Charts (light theme, `reporting/color_scheme.py` LightChartColors):
  plot bg `#f8f9fa`, median red `#e74c3c`, mean yellow, p25 purple
  `#9b59b6` / p75 green `#2ecc71`, IQR teal fill, sim paths blue `#3498db`.
- Rich components: score displayed big as **41.6/100**, medal icons,
  expandable "View Details & Metrics", persona profile cards with
  one-line descriptions, orange sliders with value bubble + currency hint
  ("→ 1 000 000 SEK").

#### WV.0 — Foundation ✅ (2026-09-07)
- [x] Design tokens: map brand into shadcn CSS vars in `globals.css` —
      `--primary` = orange (+hover), headings/foreground toward navy,
      `--secondary`/muted surfaces = `#F4F6F8`; info/warning banner
      utility classes. Keep light as the designed theme (old app was
      light-only); dark stays functional but is not the target look.
- [x] Brand assets: copy `mokara_logo.png` from the old repo →
      `web/public/`; favicon + og-image from it.
- [x] `SiteHeader` v2: logo mark + "mokara.ai" wordmark (+ tagline on
      desktop), orange active-link states. `SiteFooter` (Stockholm line) on
      all pages. Dismissible Early-Access banner (localStorage) fed by
      `/beta-status`.
- [x] Chart theme module (`lib/chart-theme.ts`): one Plotly layout+color
      preset matching LightChartColors (median red, p25 purple, p75 green,
      teal IQR fill, blue sampled paths) — used by every Chart call.
- [x] `InfoBox` / `WarningBox` components (soft blue / soft yellow, emoji
      slot) replicating the old `st.info`/`st.warning` look.
- [x] Slider v2 in `ParamField`: orange track, value bubble above thumb,
      currency hint line for `is_currency` params, proper Tooltip (shadcn)
      for param descriptions instead of `title=`.

#### WV.1 — Page by page (2026-09-07: all pages done at desktop; 375px pass pending)
- [x] **Landing + Dashboard (the old Home)**: authed → "Welcome back,
      {name} 👋", stat pair (Simulations Run / Strategies Created), recent
      simulations list (real history rows), Quick Actions row with the
      orange "🚀 Run New Simulation" CTA; anonymous → hero with logo,
      tagline, early-access spots + sign-in CTA. Landing redirects authed
      users to /dashboard.
- [x] **Login**: logo + tagline above the card; orange primary buttons.
- [x] **Simulate**: sections as collapsible accordions like the old
      expanders (⚙️ Simulation Settings, Economic Assumptions, Tax
      Settings); orange sliders w/ value bubbles; per-param help tooltips;
      currency hint under Initial Investment; sticky bottom run-bar with
      inline progress. FUNCTIONAL: the sim-limit flow — when the user is at
      their tier's simulation cap, show the old confirm-delete-oldest
      dialog before running (old `_confirm_and_delete_sims`).
- [x] **Results — FULL REPORT PARITY (the big one)**: replace the bespoke
      3-chart page with the old app's complete report, by running the same
      engine renderer server-side: new `GET /simulations/{hash}/report`
      executes `regenerate_ui_results` with a local queue and returns the
      ordered item stream (types: intro/text/plotly/dataframe/
      key_value_table/key_stats_table/settings_table/advanced_stats_table/
      glossary/warning/error), Plotly figs serialized via
      `plotly.io.to_json` — identical charts, sections, and light theme
      by construction. ttl_cache by hash. React item renderers per type,
      grouped by section like `ui/simulation_results.py`.
- [x] **My Simulations**: richer preview cards — preview stats, verdict
      accents, status chips, orange primary "New simulation". Compare tab:
      **DROPPED** (decided 2026-09-06, not wanted).
- [x] **Leaderboard**: entry cards instead of a bare table — medal, name,
      category, big **score/100**, expandable details with sub-score bars
      AND the radar chart (engine's radar_chart_data + reporting/
      radar_chart_data.create_radar_chart served as plotly JSON);
      score-components explainer ("How scores work"); "🧠 Wisdom of the
      Crowd" InfoBox; ISK-tax WarningBox; persona profile cards with
      descriptions (extend /leaderboard/meta).
- [x] **Strategies**: branded placeholder until W5 ships (logo, one-line
      pitch, "the AI designer is being rebuilt" + link to leaderboard).
- [x] **Docs**: emoji page titles, InfoBox for key callouts, brand link
      color; otherwise typography is fine.
- [x] **Settings**: parity with old ⚙️ Settings & Profile — profile block
      (avatar/name/email/plan), currency preference, AND **public username**
      (shown on leaderboards): text input + 🎲 Random generator, saved via
      the engine's display-name functions. API: extend /me + settings
      endpoint.
- [x] **Admin**: light touch — brand header/footer, orange primaries,
      consistent page titles.
- [ ] **Mobile pass**: hamburger/sheet nav for <md (replaces the old app's
      bottom-nav hacks properly); every page checked at 375px.

**Scope note (2026-09-06):** Oscar's bar is *"UI looks the same, with all
functionality we had in Streamlit"* for every page except Strategies (W5).
Compare tab explicitly dropped. Anything else found missing during the page
passes gets added here, not silently skipped.

#### WV.1b — Functional-parity sweep ✅ (2026-09-08)

Full page-by-page audit of old code+UI vs new; every functional gap closed
(landing/home fully rebuilt from pages/0_Dashboard.py via GET /home,
simulation preview cards w/ mini charts, interactive Assets explorer,
Methodology mermaid flowchart, About completed). Remaining deliberate
differences + motivations documented in **PARITY_REPORT.md**.

#### WV.2 — Exit checks
- [ ] Side-by-side screenshot review vs the old app, page by page (Oscar
      eyeballs — visual verdicts are his).
- [ ] `npm run build` + lint clean; dark mode still functional (not the
      designed theme, but must not be broken).

### W7 — Deploy (Cloud Run + Cloud SQL)
- [x] Dockerfiles for api/worker/web; decide worker topology (own Cloud Run
      service vs. same container as api). → **Decided: own service**
      (`--no-cpu-throttling`, min=1; sidecar would be CPU-throttled outside
      requests). One image serves api+worker (command override); `worker.py`
      grew a stdlib health listener for Cloud Run's `$PORT` requirement.
      Rationale + full runbook in [deploy/DEPLOY.md](deploy/DEPLOY.md).
- [x] Secrets as env vars in the host — never in the repo.
      `deploy/setup-infra.sh` pushes values from the operator's shell to
      Secret Manager; `deploy/deploy.sh` wires them via `--set-secrets`.
      Also: `web/.env.example` was never actually committed — now tracked.
- [ ] Restore-from-backup path: prod DB dump lives at
      `~/dev/mymontecarlo/backups/` — decide whether new prod starts from
      it or fresh. (Options written up in DEPLOY.md §3 — **Oscar's call.**)
- [ ] Point mokara.ai; smoke test; announce. (Checklist ready in
      DEPLOY.md §5–6; blocked on the billing/deploy go-ahead.)

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
| 2026-09-07 | WV | Foundation + all pages done at desktop, browser-verified: brand tokens (orange/navy), logo header + tagline, footer, early-access banner, InfoBox/WarningBox; **full report parity** via GET /simulations/{hash}/report streaming the engine's own item stream (13 interactive charts incl. the Portfolio Health gauges) rendered by typed React renderers with the old chapter/appendix grouping; simulate accordions w/ orange value-bubble sliders + tooltips + currency hint + sim-limit delete-oldest 409 flow; dashboard = old Home (welcome/stats/recent/quick actions); leaderboard rich cards (score/100, sub-score bars, on-demand radar endpoint, Wisdom-of-the-Crowd + ISK boxes, persona cards); settings profile + public username w/ 🎲 Random (engine generator); strategies branded placeholder; docs emoji titles. Remaining: mobile 375px pass + Oscar's side-by-side eyeball (WV.2). |
| 2026-09-06 | — | Remaining decisions closed: Cloud Run + Cloud SQL, tier system ported as-is, full rebrand to Mokara. All decisions made — W0 is unblocked. |
| 2026-09-06 | W5 | Hold lifted: agentic-generation design settled and written into the W5 section (LangGraph, one graph for create+evolve, validation ladder w/ paired baseline, spec-conformance-only rework, per-run credit metering). Implementation not started. |
| 2026-09-06 | W5 | BUILT on `feature/w5-agentic-strategies` (worktree, 5 commits: engine prep → DB → graph → API → web). 204 api tests green (+2 skipped) incl. graph/API e2e on the canned LLM; full designer flow browser-verified (create→clarify→review→save, refine, discard, rehydration banner, detail test-flight w/ chart). NOT merged — awaits Oscar's review + explicit merge go-ahead. No Gemini key on this machine: live-LLM run still unvalidated; set GEMINI_API_KEY and unset MOKARA_FAKE_LLM to go live. deps: langgraph 1.2.11 + checkpoint-postgres 3.1.2. |
| 2026-09-08 | W5 | REVIEWED + MERGED to main (`0fcc191`, pushed). /code-review at high effort → 10 confirmed findings, all fixed on-branch (`a29d133`): sandbox `__builtins__` escape (pinned + guarded import allowlist + regression tests), evolve-seed ownership 403, /test owner-only + sim-size params stripped, RNG lock + state restore around seeded paired sims, atomic needs_input→running claim + startup orphaned-run reconcile, generation-time-only category strictness, review-loop fixes (budget 24, attempts reset, over-budget → needs_input, NaN-safe trace), credits charged after start, retrieval FK join + is_published_to_leaderboard gate; web: SSE no-buffering headers, RSC res.ok guards, ?evaluate=1 honored. Gates on merged main: 212 api tests green (+2 skipped), lint + build clean. Branch + worktree deleted. Still open: real GEMINI_API_KEY live run; deferred non-blocking review notes (efficiency/simplification) surfaced to Oscar in-session. |
| 2026-09-12 | W7 | Deploy scaffolding BUILT on `feature/w7-deploy` (stacked on `fix/worker-pdf-storage-backend`, which reroutes the worker's PDF save through db/pdf_storage — it wrote local pdf_cache/ directly, broken on Cloud Run's ephemeral disks). Dockerfiles: api+worker share one python:3.14-slim image (worker = command override; worker.py gained a stdlib $PORT health listener, smoke-tested), web = node:22-alpine multi-stage on Next `output: "standalone"` (lint+build clean). Worker topology DECIDED: own Cloud Run service, `--no-cpu-throttling` min=1 (sidecar would throttle outside requests). deploy/: config.sh + idempotent setup-infra.sh (Artifact Registry, Cloud SQL PG17, GCS bucket, dedicated mokara-run SA, secrets from operator shell → Secret Manager — zero secret values in repo) + deploy.sh (Cloud Build, git-SHA tags, --set-secrets) + DEPLOY.md runbook (migrations via SQL proxy, domain, smoke checklist, rollback). Found: web/.env.example was referenced by README but never committed — now tracked. NOTHING DEPLOYED — no docker locally, images unbuilt; awaiting Oscar: billing go-ahead + DB seed decision (dump vs fresh, DEPLOY.md §3). |
| 2026-09-12 | W7 | REVIEWED (/code-review high, 8 angles) → 10 confirmed findings, all fixed on-branch: python:3.13 base (numpy has no cp314 wheel — 3.14 build would fail), .gcloudignore upload filters (builds submit ignores .dockerignore — api/.env + 741MB .venv would have hit the staging bucket), GCS init failures now fatal instead of silently falling back to local ready-but-unreadable PDFs, PDF errors write pdf_status='failed' (+test), DISABLE_API_DOCS=1 in prod (/docs+/openapi.json were public; DEPLOY.md claim corrected), api runs no-cpu-throttling min=1 (W5 generation daemon threads die under throttling/scale-to-zero — queue-based fix listed as follow-up), GEMINI_MODEL_STRONG + monitoring project/region env now set, setup-infra re-runs sync the SQL password, DATABASE_URL percent-encodes it, web/.env.example port 3100. Deferred to DEPLOY.md follow-ups: IAM/ingress api hardening, generation→job-queue port, worker heartbeat liveness, retention sweep + GCS PDF orphan cleanup (dead pdf_worker_process owns both today). Gates: 214 api tests green, web lint+build clean. Awaits Oscar's review + merge go-ahead. |
| 2026-09-12 | W7 | MERGED to main per Oscar (`9848cb8` fix branch, `fb0bda2` deploy branch); 214 api tests green on merged main; branches deleted. Deploy itself still pending: DB seed decision (DEPLOY.md §3) + billing go-ahead, then setup-infra.sh → migrations → deploy.sh all → domain → smoke test. |
| 2026-09-12 | W5 | Strategy-page extension MERGED to main per Oscar (`25cfc8f`, after merging in main's W7 work): detail page gets the old Streamlit sub-menus as tabs — Overview (publish/unpublish w/ evaluated-guard, clone incl. built-ins, params, code, mermaid flowcharts, usage badges), Evaluation (score + radar + component grid + scenario table; not-evaluated/in-progress/done states; ?evaluate=1 lands here), Test (test flight moved), History (evolution timeline + genesis). List page groups built-ins; old API sub-tab ported to /docs/strategy-api. Infra fixed at depth: evolution history now DB-native (V37 JSONB, savepoint-guarded append; git-metadata store was unconfigured so evolve requests were silently dropped) and built-ins synced at startup DB-only under a pg advisory lock (rows never existed in mokara). /code-review high → 10 confirmed findings, all fixed pre-merge (`0add40b`): timezone-shadowing broke git-mode saves, evolution append could roll back whole saves on unmigrated DBs (NOTE: run migrations before deploying V37), dead deleted_at guard let deleted strategies publish, builtin eval fallback could serve a user's same-named strategy (is_custom filter), targeted in-progress SQL replaces newest-50 job scan, 0.0-score publish 409, poll-loop/auto-queue resilience, startup-sync race + surprise-GitHub-write guards, conftest purge guarded to local/test DBs (repeated runs were exhausting max_beta_users). Gates on merged main: 219 api tests green, web lint+build clean, browser-verified. Deferred: shared MetricGrid/ScenarioTable components, radar rebuilt per poll, SHA-key builtin evals at sync time, clone-endpoint tail dedup. |
