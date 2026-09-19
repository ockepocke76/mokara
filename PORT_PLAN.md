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
- Strategy Q&A (decided 2026-09-19): one Q&A service for two subjects —
  a designer build (its generation run's persisted artifacts) and a
  completed simulation (its saved results) — so "why did it do that?"
  works in the designer (create and evolve) and on any report. Answers
  **may be prescriptive** (the one exception to the descriptive-only
  rule, see W5). Every question is triaged first (fast tier); off-topic
  questions get a fixed refusal and cost nothing; answered questions cost
  one AI credit. Generated strategies must record numeric `state_*`
  decision metrics each year (engine passthrough + blueprint contract) so
  "why did the trigger never fire?" is answerable from data, not guesswork.

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
  investment advice. **Deliberate exception (2026-09-19): the strategy
  Q&A.** When the user *asks* "what would need to change?", the answer
  may propose concrete parameter values or rule/code changes — that is
  the question's whole point, and the suggestion feeds the designer's
  refine step. The exception is scoped to the Q&A answer prompt
  (`api/app/qa/prompts.py`); analyze/explain copy and every UI string stay
  descriptive.

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
~~Still open: evolve code shown as full block, not a diff view~~ DONE
2026-09-15 (evolution-path rework — see progress log): evolve now runs
dedicated prompts (change spec → edit plan → minimal in-place edit of the
seed class) and the code card shows a before/after diff view.
Still open: pre-run credit count on the Generate button (429 is handled,
count isn't shown). ~~Evaluation charts on the detail page~~ DONE 2026-09-12: the
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
| 2026-09-13 | W5 | Generation-agent fixes MERGED per Oscar (`377293b`), root-caused by replaying the first real user's failed lifecycle run live: (1) ENGINE BUG — SandboxedStrategyWrapper never forwarded reset(), so strategy state (retirement flags) leaked between simulated paths; the backtest path runs first, and once it retired every Monte Carlo path started pre-retired at year 1 — the exact 'premature retirement' the analyze node kept reporting; smoke tests now use run_simulation's strategy_factory (fresh instance per path, evaluation-style immunity) + wrapper forwards reset(); (2) smoke-test capital now category-aware (mirrors STANDARD_EVAL_PARAMS) AND blueprint-chosen (plan.test_initial_investment, clamped 0-10M — a from-salary lifecycle spec needs a near-zero start), paired baseline gets identical capital, full evaluation stays standardized; (3) prompts: ENGINE_MECHANICS block (interest/fees/taxes are engine-charged via mandatory_costs — reviewer demanded strategies deduct interest themselves), analyze receives the test capital + treats condition-limited observability as a note not a mismatch; (4) one budget-counted retry on malformed LLM JSON (a glitch killed a run at spec stage); (5) History tab shows ALL human input verbatim (runs timeline: original request, clarify answers, refine feedback — owner-only; genesis = verbatim create request, was the AI restatement; resume payloads now persisted to events). Validated live: the failing lifecycle prompt completes on the first review pass (strategy 336: $10k start, career phase runs, leverage borrows to 30% LTV, worst path honestly never retires). Gates on merged main: 248 api tests, web lint+build. |
| 2026-09-12 | W5 | Designer "How it works" flowchart MERGED to main per Oscar (`54c1ef7`): collapsible Mermaid diagram on `/strategies/new` mirroring the generation graph (stages from STAGE_LABELS, clarify/rework/refine loops, three endings); chart lazy-mounts on first open so the entry form never loads mermaid unopened. /code-review high → 3 confirmed findings fixed pre-merge (eager mermaid load, STAGE_LABELS drift, MermaidChart swallowed render errors — now logged). Gates: web lint+build clean, diagram render browser-verified. Deferred notes: retry counts ("3 attempts/rounds") mirror graph.py constants by hand; crash/budget failures bypass the drawn rework path (accepted simplification). |
| 2026-09-12 | — | Full-codebase review + R1 security wave MERGED to main per Oscar (`011b8a5` tracker, `0ad0195` web, `2de510f` api-access, `709c92d` sandbox). CODE_REVIEW_2026-09-12.md added: R1-R6 tracker (security, correctness, Cloud Run, deletion pass, refactors, performance) from a four-pass deep review; R3 annotated for what W7 already resolved. R1 landed: (R1.1/R1.2) sandbox hardened — pandas/numpy behind policy proxies (pickle/file/eval families + gateway submodules blocked, from-import bypass covered), validation dry-runs in a spawn subprocess under timeout+rlimits; branch review (8 angles) found+fixed a PoC'd guard-rebinding hole (`global _getattr_` poisoned shared globals — global banned, guard names reserved, per-call exec globals), removed the unguarded second dry-run, made the worker respect run_and_save_simulation's failure return (failed sims no longer complete jobs), moved SIGTERM registration out of import time. (R1.3) rehype-sanitize on shared Markdown (stored-XSS on cross-user descriptions; browser-verified payload strip). (R1.4) AUTH_DEV_LOGIN hard-gated out of prod builds. (R1.5/R1.6) simulation access rules: reads own-or-public, mutations own-only, all "my history" paths filter by owner (overflow-delete could pick others' public rows); review caught the ungated preview endpoint (verified live) — fixed; hmac.compare_digest on the internal secret. Gates on merged main: 244 api tests green, web lint+build clean. Residuals tracked in CODE_REVIEW R1: deny-list→allowlist follow-up, simulation-time runaway backstop (→R2.1), designer-loop spawn cost (→R3.3). |
| 2026-09-13 | — | R2 correctness wave MERGED to main per Oscar (`126f584` job pipeline, `66ca0fc` migrations, `05090bb` report single-flight); 257 api tests green on merged main; branches deleted. R2.1: heartbeat-based stale-job recovery (V38 heartbeat_at, 30s worker beats; reclaim only after 5min silence — never-heartbeated rolling-deploy jobs get their full timeout_seconds first, review-caught) + owner fences on complete/fail/retry/progress (zombie workers can't clobber reclaimed jobs) + runaway-but-live jobs FAIL at their timeout_seconds (hard SLA; results may still land in the shared cache — accepted). R2.2: simulation progress wired to the job row (UI progress bar now real). R2.3: migration runner advisory-locked + fail-fast, per-job run removed (worker migrates at startup), run_migrations.py de-crufted for CI; review-caught lock-leak-on-aborted-transaction fixed. R2.4: 32-stripe single-flight on report rendering. R2.5: cache staleness computed in SQL (UTC-safe). Tracker updated in CODE_REVIEW_2026-09-12.md. |
| 2026-09-14 | — | R4 deletion pass MERGED to main per Oscar (net −3,919 lines, 9 commits; 247 api tests green on merged main). Gone: Streamlit-era process entry points in background_tasks (−462), dead reporting modules/builders (−875), the never-functional Cloud Monitoring layer (−500), the GitHub-as-strategy-store subsystem (−1,130; save_custom_strategy is now a plain transactional upsert — closes R5.1's nested-connection hazard), the single-implementation DB abstraction incl. the regex placeholder-translation cursor wrappers (−630), logger's Streamlit filters + ui_interaction.log (+ LOG_TO_FILES=0 prod gate → closes R3.6), require_user triplication, MyMonteCarlo branding. Latent bugs surfaced+fixed: perf/slow-query config flags never read config.yml; update_cached_simulation_params was a silent no-op all PG era; limits/user_profile depended on the deleted `?`-translation wrapper (now native). Reviews: liveness sweep over all 26 deleted symbols + behavior-preservation pass with live-DB smoke tests — both clean. Leftovers noted in tracker: deploy.sh's inert GCP_MONITORING_* env, dead core/db_logger.py. |
| 2026-09-15 | — | R5 refactor wave MERGED to main per Oscar (`292a70d` db contextmanager, `9c26709` cn, `10e4351` polling hooks, `47ba9b4` error story, `45c4ec0` evaluation component); gates on merged main: 247 api tests green, web lint+build clean, key flows browser-verified on an integration build. R5.2a: 64 postgresql_db methods on one connection-lifecycle contextmanager (−259 lines; AST-verified zero semantic change, 5 special-case methods left verbatim). R5.3: clsx+tailwind-merge restored, `cn` micro-dep removed (turned out behavior-equivalent — supply-chain hygiene), shadcn CLI → devDeps. R5.5/R5.6: usePdfDownload + useJobPolling replace four hand-rolled loops; simulate-form's unbounded poll leak fixed; review-driven: failure cutoff ~60s with backoff (was 12s). R5.7/R5.8: root error/loading boundaries, dashboard skeleton, one SignInGate for six bespoke gates; getViewer degrades to anonymous on outage — review caught it swallowing Next's dynamic-rendering signal (static logged-out prerender risk; unstable_rethrow) and degraded sessions masquerading as logged-out (degraded flag + fail-loud on auth-branching pages, admin force-dynamic). R5.4: shared EvaluationRadarScores/ScenarioTable; categoryLabel → lib. Remaining R5 (tracker): R5.2b domain split, R5.9 chart theme, R5.10 engine bits. |
| 2026-09-15 | — | R5.2b MERGED to main per Oscar: PostgreSQLDatabase (2,636 lines) split into domain mixins under db/postgresql/ (core/users/simulations/strategies/leaderboard/jobs/system) assembled into the same class — import path, facade and all call sites unchanged. Bodies moved by AST line-range extraction, 81/81 methods byte-identical vs main except two required Path(__file__) depth fixes (verified to resolve identically). Structural review clean (no circular imports, zero MRO collisions, ttl_cache tail intact on the singleton). 247 api tests green on merged main. |
| 2026-09-16 | — | R5.9 MERGED to main per Oscar (`fae4a4f`): web/lib/chart-theme.ts deleted — it had zero importers and had silently drifted (claimed LightChartColors, carried the dark palette's hexes); reporting/color_scheme.py is the documented single source (figures arrive fully styled in the API's plotly JSON). Engine: plotly template installs lazily via ensure_plotly_template() (called by all 12 builders + the report/PDF pipeline entries) instead of as an import side effect; frozen Theme global and get_theme_from_config removed. Verified: 254 api tests green, web lint+build clean, full report regenerated against the branch api — all 13 figures carry the light template — and browser-rendered (gauges/charts correct). |
| 2026-09-17 | — | R5.10 MERGED to main per Oscar — R5 COMPLETE. Sandbox: the source-level regex that rewrote in-place assignments (and corrupted **=, //= into syntax errors) is gone; plain names use a real _inplacevar_ dispatch, attribute/subscript targets (self.x += 1, d[k] += 1) desugar at the AST level in the policy (RestrictedPython forbids them natively; the regex had enabled them by accident). Security-review probed: loads/stores stay guarded, __dict__ tricks rejected, _inplacevar_ unreachable from strategies; deliberate semantics fix: lst += now mutates like real Python. simulation.py → core/simulation.py (17 importers); review caught version.py's COMPONENT_MAP still hashing the old path (drift warning would never fire again) — fixed+verified. sandbox_tester plotting had already moved client-side (no action). Gates: 270 api tests green on merged main (incl. the version-DAG feature that rode along), web lint+build clean. |
| 2026-09-13 | W5 | Designer-flow marketing section MERGED to main per Oscar (`2947498`): "🤖 Inside the AI Strategy Designer" section (marketing copy + shared flowchart + CTA) on both the guest landing and logged-in home (dashboard/page.tsx), flow definition shared from components/designer-flow.tsx. /code-review high → root-cause fix applied: MermaidChart itself now lazy-loads the mermaid bundle when its container nears the viewport (a closed <details> defers until opened), replacing two bespoke per-caller guards and making the methodology + strategy-detail charts lazy for free; STAGE_LABELS hoisted to leaf module web/lib/stage-labels.ts (re-exported from strategies/model.ts) to keep the landing bundle decoupled; shared caption; spacing derived from authenticated. Gates: web lint+build clean on merged main (incl. R2 web changes). Browser-verified: section copy/CTA/layout + diagram SVG render; the observer-fires-on-visible step is unverifiable in the hidden preview pane — worth a quick visual glance on :3100. |
| 2026-09-15 | W5 | Evolution path rework MERGED to main per Oscar (branch `feature/strategy-evolution`; merge resolved against R5.2b's db domain split — the save_custom_strategy/get_strategy_evolution_history changes ported into db/postgresql/strategies.py): evolving a strategy now edits it instead of regenerating it. Root cause (reported by Oscar: "change a default" produced a whole new strategy): seed code reached only extract_spec, whose lossy prose spec fed the from-scratch plan/generate prompts, and the rewrite overwrote the seed row with no snapshot. Now: evolve-specific prompts (evolve_spec → change list + change_scope [parameter_only/behavioral/structural], evolve_plan → edit list against the seed code, evolve_generate → minimal in-place edit, same class name, no outside examples); structural falls back to the create pipeline (still saves into the seed row). Deterministic backstops in validate: difflib drift limit (30%/70% by scope) + parameter-set equality for parameter_only, surfaced as a "minimal_change" safety check; failures rework with restart-from-original feedback. Test flight pairs against the SEED on identical markets ("X (before this change)"); analyze judges "change visible + everything else tracks the baseline". save_custom_strategy snapshots previous_code into each evolution_history entry (stripped from the history API payload). Web: change card ("What will change — parameter values only / Everything else stays exactly as it is"), seed-only examples card, code card diff view (colored unified diff, "View the changes — N lines"), minimal_change check label. Gates: 250 api tests green (3 new evolve e2e tests: minimal edit, structural fallback, rewrite caught by guard + seed untouched), web lint+build clean, browser-verified end-to-end on worktree dev servers (fake LLM): 4%→5% default evolve produced a 2-line diff, all checks green, saved in place with history snapshot. Not yet run against real Gemini. /code-review high (8 finders + 10 verifiers) → 10 findings (8 CONFIRMED), all fixed on-branch except one design question, in `2a00766`/`dcd7008`/`ba5a828`: drift-ratio guard replaced with method-level AST comparison (measured: rewrites scored 0.12–0.18 drift, UNDER both limits, while autojunk pushed a quote-style change to 0.73 — the ratio was useless both ways); verbatim-seed no-op output now rejected; change_scope normalized + `changes` required (legacy-checkpoint fallback); revise_spec schema restored (clarify could drop change_scope); review-refine on evolve re-enters at extract_spec (frozen scope made out-of-scope refines unsatisfiable and lost the accepted candidate; budget → 30); analyze no longer asserts a baseline that didn't run; clone snapshots COALESCE parent code; history endpoint strips code blobs in SQL; honest behavioral copy + check label. Final gates: 254 api tests green (4 more evolve tests), lint+build clean, refine re-spec browser-verified. OPEN DESIGN QUESTION for Oscar (finding 8, deliberately not changed): a `structural`-scope evolve still rebuilds from scratch and overwrites the seed row in place on one fast-tier classification — alternative is saving structural results as a NEW strategy row (parent-linked), leaving the seed immutable. Known edge: evolving a strategy to a state it is already in ("set to 5%" when it is 5%) now fails after 3 attempts with "change was never applied" rather than silently saving a no-op. AGREED FOLLOW-UP (Oscar, 2026-09-15): version-DAG storage in Postgres — STRATEGY_VERSIONS(content_hash, code, parameters_json, parent_version_id, source, request) + head_version_id on CUSTOM_STRATEGIES; clone = head pointing at the shared version, evolve = child version (DAG branch), revert = head move; backfill from evolution_history previous_code, then retire the JSONB snapshots; evolution-tree viz on top later. Git semantics without the GitHub store the R4 pass deleted. |
| 2026-09-16 | W5 | Version DAG MERGED to main per Oscar (2026-09-17, `160aed4`; branch `feature/strategy-version-dag`, the follow-up agreed 2026-09-15): git semantics for strategy code, DB-native. V39 STRATEGY_VERSIONS (content hash, code, params, class_name, parent pointer, source, request) + head_version_id branch ref; every code-changing save appends a node in the save transaction (identical content deduped; headless rows self-heal with a backfill parent). Clone = head POINTING at the parent's node (zero copy); evolving a clone forks the DAG at the shared ancestor. Revert = append-only restore (ownership + ancestry enforced; ancestry walk stops at other users' strategies, so clones never see the donor's private iterations; a row diverged from its own head is repairable by restoring the head). Startup backfill (advisory-locked, idempotent) reconstructs legacy chains from the old previous_code snapshots then those stop being written. API: GET /strategies/{id}/versions (owner-only) + POST /strategies/{id}/revert, BFF-proxied; History tab gains a Versions section with confirm-then-Restore. Found+fixed live during verification: cloning your OWN strategy destroyed it (name-keyed upsert matched the original row; is_clone_unedited nulled its code) — clone names now suffix on collision, regression-tested; the version DAG made the destroyed row recoverable, which is the feature's whole point. Gates: 263 api tests green (10 new: DAG chain/fork/dedup, revert ownership+ancestry+repair, backfill idempotency, self-clone regression, API owner-gating), web lint+build clean, browser-verified on worktree servers (create → evolve → clone → fork → revert incl. through the UI's Restore button). Evolution-tree viz still to come on top. /code-review high (8 finders + 5 verifiers; 2 candidates REFUTED: head-move race — the pre-version UPDATE's row lock serializes; user-deletion orphans — no reachable hard-delete path exists, noted as latent for whoever builds account deletion) → 10 CONFIRMED findings, ALL fixed in `86128d9`/`6d3cbb0`: ancestry reworked to expand-from-owned-only (clone-then-evolve was unrestorable — the flagship flow; and the anchor leaked the donor's evolve prompt to cloners — now SQL-redacted with an "inherited" badge); fail-closed versioning (only pre-V39 schema tolerated; anything else re-raises — silent row/head divergence eliminated) with transitional previous_code snapshots on unmigrated DBs and revert refusing when it can't record; revert also refuses pure clones (was silently materializing them), COALESCEs params (restoring a backfill node wiped the parameter schema + broke the evaluation-hash link) and stops stamping 'validated' on never-validated backfill code; backfill probes an indexed predicate before locking and rolls back before unlock (a pre-V39 API boot leaked the session advisory lock and wedged every later startup); builtin_sync now versions its writes (stale heads let clones "restore" pre-deploy builtin code); clone collision guard sees soft-deleted names via a cheap query (trash-name clone resurrected+destroyed the deleted row; also dropped the every-public-strategy code fetch). Final gates: 265 api tests green (4 more: cross-user fork restore + redaction, trash-name clone, pure-clone revert refusal, backfill param reconstruction + restore), lint+build clean, UI re-verified. Deferred (named in review, pre-existing): save_custom_strategy's name-keyed upsert still lets a same-named CREATE run overwrite silently — right fix is a partial unique index + explicit insert/update intent; evolution_history is now a redundant third timeline (candidate for V40 retirement); update_custom_strategy bypasses versioning (zero callers today). |
| 2026-09-17 | W5 | Lineage viz Phase 1 MERGED to main per Oscar (2026-09-17; branch `feature/strategy-lineage-viz`): the strategy History tab draws the version DAG as a Mermaid graph. get_strategy_lineage = ancestry spine (same granted/redaction semantics as the versions list) + all descendant nodes on the requester's OWN live strategies (their forks; other users' forks stay invisible) + head markers naming which strategy each node is current for; shipped on the existing /versions response (no extra round trip). Web: LineageGraph (reuses the lazy MermaidChart) above the Versions list — blue own line, yellow-dashed clone boundary, grey own forks, plain-language labels; hidden when the history is a straight line; labels sanitized before entering Mermaid source. Gates: 272 api tests green (2 new: own-fork graph w/ head markers, other-users'-forks exclusion; endpoint nodes asserted), web lint+build clean, browser-verified on worktree servers against the real forked dev-DB strategies (983/997: spine + fork branch + head markers rendered; owner-gating 404 confirmed). Phase 2 (public cross-user family tree, strategy-level + leaderboard descendants badge) still to come. /code-review high (4 combined finders) → 10 findings (all CONFIRMED, all fixed in `31f4920`/`cc268de`): head markers compared truncated NAMES not ids (a ≥24-char name's clone labeled a foreign node "current version"); foreign boundary nodes shipped parent_version_id (a pointer into the donor's private chain — now redacted + regression-tested); spine annotations landed on discarded copies (versions[]/nodes[] disagreed on heads); spine+fork+heads reads spanned two connections/snapshots (concurrent save drew the fresh head as a parentless fork — now one cursor); fork walk stopped at soft-deleted strategies (amputated live branches — now pass-through, flagged); mermaid securityLevel pinned 'strict' (innerHTML dependency documented) + raw source-label fallback cleaned; legend now generated from on-screen classes with honest wording (old copy reversed history's arrow for clones) and header de-jargoned; fork nodes text-labeled with their strategy name (a11y, consumes the shipped field); payload de-duplicated (versions+forks disjoint) + memoized builder + 80-node cap; source-label map hoisted to web/lib/version-source-labels.ts. Final gates: 273 api tests green, lint+build clean, graph re-verified in browser (id-based markers, named forks, conditional legend). |
| 2026-09-17 | W5 | Custom strategies wired into the main Run Simulation flow, on branch `feature/simulate-custom-strategies` (worktree) — merged into main per Oscar after a rebase-merge past the version-DAG/lineage-viz/R5.10 work above (simulation.py's move to core/ and the sandbox in-place-assignment fix both predate this branch's rebase; no conflicts in engine code, only this file). Root cause (Oscar reported: saved a strategy via the designer, couldn't select it under Run Simulation): `/config/params`/`/simulations` only ever knew about the 3 built-in classes; a full `strategy == 'custom'` execution branch already existed in `background_tasks.py` (sandboxed via `SandboxedStrategyWrapper`, same `run_simulation` engine as everything else) but was dead code — nothing ever reached it. Now: `/config/params` unions in the caller's own + public custom strategies (`custom:<id>`, grouped Built-in/My Strategies/Community; not-yet-`validated` ones shown disabled with a reason instead of vanishing); `/simulations` resolves that id via a fresh DB lookup + ownership check (`_owned_strategy`) before injecting code/class_name/params into the run — never trusts client-supplied code. Web: grouped `<Select>`, plain numeric input (not a slider) for custom params, which carry no min/max. /code-review high (8 finders, single-pass verify) → 10 findings, 7 CONFIRMED fixed on-branch: **critical** — a bare `strategy: "custom"` (vs `"custom:<id>"`) skipped the ownership/validated-status gate entirely, letting any authenticated user run arbitrary sandboxed code with no check (now: client-supplied `custom_strategy_*` fields are stripped up front, bare `"custom"` rejected); excluding `custom_strategy_id` from the simulation-cache hash let two different strategies with identical code (e.g. two users' unedited clones of the same public template) collide onto one cached result, leaking one strategy's name/description into the other's report (id now stays hashed, only display text — name/description/ai_description — is cache-free); a hardcoded flat 2000 `num_simulations` cap ignored the already-built but previously-unused per-tier `LimitEnforcer.get_mc_iterations_limit`/`max_mc_iterations_custom` (now wired in, incl. clean 403 when a tier disallows custom runs); non-numeric `num_simulations` 500'd instead of a clean error; a validated row with null `class_name` would fail deep in the sandbox instead of at submit time; `custom_strategy_param_defs`/`custom_strategy_params` were never populated, leaving the PDF settings table and Gemini prompt empty for every custom-strategy report; `reporting/content.py` read the wrong key (`ai_description` vs `custom_strategy_ai_description`) for the AI description shown in the PDF. Also fixed pre-existing (previously-dead-code) bugs surfaced by making this path reachable: `pdf.py` (×2) and `reporting/components.py` checked the wrong sentinel `'custom_strategy'` instead of `'custom'`, which would have shown "Custom" instead of the real strategy name in every report. Deferred (non-blocking, surfaced to Oscar): `/config/params` fetches every public custom strategy's full code + an evaluation JOIN, unpaginated, on each `/simulate` load (matches the existing `/strategies` query pattern, not a new problem class); the `if strategy == 'custom'` display-name special-case is now duplicated across 4+ files with no shared helper (this PR had to fix 3 already-drifted copies); strategy selection is a parsed `"custom:<id>"` string rather than a structured field (deliberate call in the approved plan). Also noticed in passing, spun off separately (not fixed here): AI analysis is failing repo-wide on a stale Gemini model name (`models/gemini-2.0-flash` retired). Gates: 267 api tests green pre-rebase (18 new/updated for this feature, incl. 2 dedicated security-regression tests), web lint+build clean, full flow browser-verified end-to-end on worktree dev servers against the real shared dev DB — a real "DAG FIRE" custom strategy ran through the production simulator to a completed report showing its correct name throughout. |
| 2026-09-17 | W5 | Family tree (lineage viz Phase 2) MERGED to main per Oscar (2026-09-18; branch `feature/strategy-family-tree`): the public cross-user clone-lineage view. get_strategy_family roots at the highest ancestor reachable through VISIBLE strategies (public/built-in/viewer's own) and walks visible descendants; invisible strategies appear only as per-node hidden_forks counts (matching the leaderboard's existing fork-count exposure); author identity = display name or 'anonymous' (never the email fallback other surfaces carry); scores join by content hash; self-link guards + depth caps. GET /strategies/{id}/family (viewable-strategy gate, invisible parent pointers nulled) + BFF. UI: 'Family tree' section on the Overview tab (Mermaid TD; blue self, purple built-ins, grey others; '+N private forks' and '(private — only you see it)' markers; link chips below the SVG since mermaid stays strict; 60-node cap). Leaderboard: descendant_count (recursive clones-of-clones) on both with-profile queries + 🌳 badge shown only when it beats the direct 🔗/🔱 counts; the no-category branch also gains the usage counts it was silently missing. Gates: 277 api tests green (4 new: privacy aggregation incl. publish transition, visible-root walk w/ email-free owner names, deleted exclusion, family endpoint incl. 404 for foreign private), web lint+build clean, browser-verified (983/997 family renders w/ privacy labels + link chips). /code-review high (4 combined finders) → 10 findings (all CONFIRMED, all fixed in `963f723`/`044c42d`/`21ae28d`), headlined by a design-breaker the finders caught: visibility keyed on is_public, which PRODUCTION NEVER SETS for user strategies (publish sets is_published_to_leaderboard) — the cross-user tree could never render for real flows and the tests fabricated the state; now one _FAMILY_VISIBLE constant (published OR public OR builtin OR own, IS TRUE forms so the hidden-count negation is provably complementary on NULL flags), _owned_strategy's read gate admits published strategies, tests use the real flag, verified live. Also fixed: published strategies were labeled "(private — only you see it)"; deleted intermediates amputated live branches (now flagged pass-through, deleted leaves pruned — the Phase-1 principle); builtin nodes leaked a platform-wide private-clone tally (now 0); builtin leaderboard rows could never get lineage badges (cs.id NULL — now resolved by name); the recursive descendant count ran per CANDIDATE row on limit=500 interactive paths across two drifting SQL branches (now one paged query, lateral counts per returned row, deleted-consistent with the badge gate); family score now = latest evaluation (was best-ever across categories); server 200-node cap + truncation flag; client fetch gated on strategy-row hints; built-in/deleted text cues on nodes; mermaid label sanitizer hoisted to web/lib/mermaid-label.ts. Final gates: 278 api tests green, lint+build clean, publish-flips-privacy verified live. |
| 2026-09-18 | W5 | Version-DAG follow-ups MERGED to main per Oscar (2026-09-18, blanket go-ahead “complete all of it in one go, then review and merge”; branch `feature/version-dag-cleanup`) — the deferred items from the DAG/family-tree reviews: (1) Leaderboard author privacy: COALESCE(display_name, email) leaked raw emails of display-name-less users to every signed-in viewer — now display name or 'anonymous' (the family-tree rule), u.email dropped from the payload entirely, built-ins keep a NULL author; regression test asserts the email never appears in a row. (2) Legacy V37 evolution timeline RETIRED (V40): the version DAG + generation runs are the two remaining timelines; V40 strips previous_code blobs only where EVERY snapshot provably exists in the row's version chain (a head alone is no proof — self-heal synthesizes one parent, the backfill never revisits headed rows, and the API process doesn't run migrations), tolerating non-array/scalar timeline values; saves append only on a pre-V39 schema (there the snapshot is the sole recovery material — reachable because only the worker/deploy/admin run migrations); restores stop appending; the frozen entries still serve the History tab's legacy fallback, now OWNER-ONLY and enforced in SQL (they carry verbatim evolve prompts — previously any viewer of a public strategy could read them); dead include_code parameter removed. (3) Name-keyed upsert ROOT-FIXED (V41): save_custom_strategy is insert-intent — a strategy_id updates that row (fails loudly if missing; deletion now WINS over an in-flight save: the update never resurrects a trashed row), no strategy_id always inserts, colliding live names suffixed via the shared utils.next_free_name (clone service uses the same helper), with a UniqueViolation retry so a name race re-suffixes instead of discarding finished work; callers report the name the row actually got (run_completed + runs table + clone result re-read it); V41 renames existing live duplicates collision- and length-safely (bounded loop), NEVER renames user-0 built-ins (exact names are join keys — duplicated builtins soft-delete stale copies instead), then adds the partial unique index (user_id, strategy_name) WHERE deleted_at IS NULL; deleted names are free to reuse. (4) Evolve path verified against REAL Gemini for the first time: seeded 4% strategy, live evolve “change the default withdrawal rate to 5%” through the actual FastAPI app (sync runner, gemini-2.5-flash fast tier + env strong tier) → paused at review, saved → a genuine 1-line minimal edit (0.04→0.05), evolve version node, params updated, no legacy timeline entry; one checks-stage rework self-recovered. (First live attempt “failed” 3× with sandbox timeouts — the harness script lacked an `if __name__` guard and the spawn-mode validation subprocess re-ran the whole script; product was fine.) Account-deletion purge of STRATEGY_VERSIONS dropped from this branch: another session's `fix/delete-user-duplication` already implements it. /code-review high (4 combined finders + 3 batch verifiers) → 10 findings (7 CONFIRMED, 3 PLAUSIBLE), 9 fixed in `c6a5b45` (headliners: update path resurrected trashed rows — with a live namesake the V41 index then failed the whole save; V40 could permanently strip snapshots the DAG never captured; V41's rename could collide/overflow and wedge every future migration, and renamed built-ins whose exact names are join keys), 1 skipped: the leaderboard commit is off-theme for the branch per “one branch = one theme” — kept per Oscar's one-go instruction, noted here. Gates: 296 api tests green (7 new), web lint+build clean (no web changes), V40+V41 applied to the local DB via run_migrations (re-applied after the review rewrite). Deferred still: real-Gemini run used the fast tier for spec/plan — strong tier exercised at codegen; evolve-to-already-true edge; R3 Cloud Run items; R5.10; R6. |
| 2026-09-19 | W5 | Strategy Q&A built on branch `feature/strategy-qa` (worktree; NOT merged — awaiting Oscar's go). Ask questions about a strategy's observed behavior with prescriptive answers, in the designer (create + evolve, at the review step and after save) and on completed simulation reports. Engine: strategies may return numeric `state_*` keys from `execute_strategy_for_year`; `Portfolio.record_yearly_snapshot` carries them into the yearly history (strings/non-finite dropped so aggregation stays numeric). Designer: the blueprint declares `state_metrics`, generate prompts require them, the test flight reworks code that never records a declared metric, and test-flight artifacts + worst-path trace carry them (evolve runs only extend the set when a planned edit touches `execute_strategy_for_year`, so the minimal-edit guard holds). Q&A: `api/app/qa/` — `QAContext` built from either a generation run (latest code/blueprint/test_flight/behavior artifacts off STRATEGY_GENERATION_EVENTS — nothing new persisted, no sandbox re-run) or a simulation (params, scalar stats, prior Gemini narrative, worst+median sampled paths incl. state rows, built-in class source via inspect); triage (fast, JSON on_topic) → answer (strong, JSON answer_md + optional suggested_change{summary, refine_feedback}); V42 QA_THREADS/QA_MESSAGES (one thread per user per subject); `/qa/thread` + `/qa/messages` behind the internal secret; BFF `/api/bff/qa/*`. UI: `web/components/qa-panel.tsx` reused by `designer.tsx` (refine feedback state lifted to BuildLog so "Use as refine feedback" fills the review textarea) and `simulations/[hash]/page.tsx` (signed-in viewers, no refine button). Gates: api suite green incl. 20 new tests (engine passthrough, rework-on-missing-metric, db round-trip, service triage/answer/credits/ownership, API auth+validation), web lint+build clean, browser-verified on worktree servers 8010/3110 with the canned provider: off-topic refusal, on-topic answer with suggestion → textarea → refine round → reload rehydrates thread → save → evolve run gets its own thread → report page panel; mobile width checked. Not yet exercised against real Gemini (prompt quality unverified). |
