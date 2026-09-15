# Codebase Review — 2026-09-12

Full-codebase review (architecture, duplication, security, Cloud Run/scaling
readiness), run as four parallel deep-review passes: API app+data layer,
engine+reporting, Next.js frontend, deployment readiness. All findings were
verified against source with file:line evidence; the two most severe were
independently re-checked.

**How to use this file:** PORT_PLAN-style tracker. Check items off as they
land, note the branch/commit next to the checkbox. Severities: 🔴 high,
🟡 medium, 🟢 low. Ordering within each section = suggested attack order.

**Overall verdict:** the port's architecture is sound and enforced — BFF
boundary intact (secret never reaches the client, all 7 routers behind
`verify_internal_secret`), job queue correctly uses `FOR UPDATE SKIP LOCKED`
with idempotency keys, and the W5 strategy-generation runner (Postgres-
checkpointed graph, DB-backed SSE event log, atomic claim on resume) is
well engineered. The debt is concentrated in the **copied engine layers**
(`db/`, `background_tasks.py`, `reporting/`) — Streamlit-era sediment that
came along in W0 — plus a handful of security findings that outrank all
architecture concerns.

Related in-flight work at review time: `fix/worker-pdf-storage-backend`
(→ R3.1) and the `feature/w7-deploy` worktree (→ all of R3). Both merged to
main before this doc landed — R3 below is annotated with what they resolved.

---

## R1 — Security (do first)

> **Status 2026-09-12:** R1.1-R1.6 implemented across three reviewed
> branches awaiting merge: `feature/r1-sandbox-hardening` (R1.1+R1.2, plus
> review fixes: `global`-statement/guard-name bans, per-call exec globals,
> single guarded dry-run, worker return-check, signal-handler move),
> `fix/r1-web-security` (R1.3+R1.4), `fix/r1-api-access` (R1.5+R1.6
> compare_digest, plus the preview endpoint gate found in review).
> Residuals now tracked at the end of this section.

### R1.1 🔴 Strategy sandbox: full `pandas`/`numpy` exposure → file read / RCE
- [ ] Wrap `pd`/`np` in whitelist proxies (or explicitly block the
      reader/eval/serialization families) instead of injecting the real
      modules (`core/sandbox.py:33-34`; the attribute guard at `:70-85`
      only blocks dunders).
- [ ] Add escape regression tests for `pd.read_pickle` (RCE via pickle),
      `pd.read_csv('/etc/passwd')`, `np.load(..., allow_pickle=True)`,
      `pd.eval`/`df.query` — `tests/test_sandbox_escape.py` currently only
      covers `open`/`eval`/`__import__`.

### R1.2 🔴 Sandbox: no CPU/memory/time limits → trivial worker DoS
- [ ] Execute untrusted strategy code in a subprocess with wall-clock
      timeout + `RLIMIT_AS`/`RLIMIT_CPU` (today: bare `exec` at
      `core/sandbox.py:452`, then `execute_strategy_for_year` called
      `num_years × num_simulations` times from `simulation.py:119-149`
      with no watchdog anywhere in the chain). A `while True:` or a big
      allocation hangs/OOMs the worker.

### R1.3 🔴 Stored-XSS: `rehype-raw` on cross-user content, no sanitizer
- [ ] Add `rehype-sanitize` with an allowlist schema to
      `web/components/markdown.tsx:11`; it renders other users' strategy
      descriptions (leaderboard `entry-card.tsx:172`, strategy detail
      `strategy-detail.tsx:87→277`). Raw `<img onerror>`/`<iframe>` passes
      through today.
- [ ] Delete the second unsanitized copy in
      `web/app/simulations/[hash]/report-view.tsx:66-72` (which also lacks
      GFM — report pipe tables render as plain text) and import the shared
      component.

### R1.4 🔴 `AUTH_DEV_LOGIN` → account takeover if ever set in prod
- [ ] Hard-gate: enable email/password only when
      `AUTH_DEV_LOGIN === "1" && NODE_ENV !== "production"`
      (`web/lib/auth.ts:12-14`). Open sign-up + the `X-User-Email` identity
      mapping (`api/app/deps.py:34-42`) means signing up with an admin's
      email owns that account, tier included.
- [ ] Document the flag in `web/.env.example`.

### R1.5 🟡 Simulation ownership/visibility holes
- [ ] `_own_history_row` (`app/routers/history.py:19-26`) matches against a
      query that includes *other users' public sims* (`db/queries.py:277`) —
      so DELETE/PDF-queue "ownership" passes for any public sim. Filter by
      `row['user_id'] == user['id']`.
- [ ] Decide explicitly: are `/simulations/{hash}/results`, `/report`
      (`app/routers/simulations.py:322,465`) and `/pdf/status`
      (`history.py:101-112`) public-by-design? Hashes are deterministic
      functions of params, not capabilities. Document or gate.
- [ ] Same question web-side: `web/app/simulations/[hash]/page.tsx:17-23`
      is the one app page with no viewer gate.

### R1.6 🟢 Small hardenings
- [ ] `hmac.compare_digest` for the internal secret (`app/deps.py:25`).
- [ ] BFF defense-in-depth: a `requireSession()` guard on mutating/admin
      BFF routes — today no BFF route checks auth before proxying
      (verified: enforcement is 100% FastAPI-side, so this is layered
      defense, not an open hole).
- [ ] Rotate the old prod DB password before reusing the dump/instance —
      it sits in plaintext in the old repo's `deploy-to-cloud.sh`
      (`DB_PASSWORD=...`), whose history is already considered burned.

### R1 residuals (from the branch reviews, accepted for now)
- [ ] Sandbox deny-list is fail-open: a future/missed numpy/pandas IO or
      eval API stays reachable until listed. Follow-up: per-module
      attribute *allowlist* (fail-closed), same shape as the module
      allowlist. (`core/sandbox.py`, `_DENIED_ATTRIBUTES`)
- [ ] Runaway strategy code whose hang only triggers under simulation-time
      conditions (or probabilistically) passes the validation gate; the
      class-body exec in the parent is also unguarded. Backstop = job-level
      timeouts (R2.1) for the worker; the API-side generation runs still
      need the R3.3 queue migration (which also removes the spawn-per-
      validate cost in the designer rework loop).
- [ ] `simulation-card.tsx` delete gives no UI feedback on 404/409
      (unreachable today — users can't own public sims); fold into R5.7's
      error-handling pass.

---

## R2 — Correctness

> **Status 2026-09-13:** R2.1-R2.5 merged to main (`126f584` job pipeline,
> `66ca0fc` migrations, `05090bb` report single-flight), each branch
> reviewed pre-merge; review fixes included: never-heartbeated jobs get
> their full timeout before reclaim (rolling-deploy double-run), rollback
> before advisory unlock (lock-leak wedge), deterministic single-flight
> tests. The simulate-form poll leak (R2.5 second item) is deferred to
> R5.6's shared hook as planned.
>
> Accepted residuals: `timeout_seconds` is now a hard SLA — a job
> finishing slightly over budget shows FAILED even though its results
> landed in the content-addressed cache (re-submit returns 'cached'
> instantly); distinct report hashes colliding on one of the 32 stripes
> serialize (rare, harmless at this scale).

### R2.1 🔴 Stale-job recovery can double-run long simulations
(Found independently by two review passes.)
- [x] `reset_stale_jobs` resets anything PROCESSING > 900s global
      (`db/postgresql_db.py:2841-2867`, called with 900 from
      `services/background_worker.py:345`) but sims are queued with
      `timeout_seconds=1800` (`services/background_manager.py:75`) and the
      column is never read → a >15-min sim is reset to PENDING and claimed
      by a second worker while the first still runs. Use
      `started_at < now() - (timeout_seconds * interval '1 second')`.
- [x] Fence completion: `complete_job`/`fail_job`/progress updates
      (`postgresql_db.py:2699-2753`) update by `id` alone — add
      `AND worker_id = %s` so an evicted worker can't overwrite the
      reclaimer's result.
- [x] Add a worker heartbeat column; key recovery on "stopped
      heartbeating", not wall-clock (also needed for R3.4).

### R2.2 🟡 Simulation job progress is dead plumbing
- [x] The worker defines `update_progress` then never passes it —
      `run_and_save_simulation` gets `progress_queue=None` and no `job_id`
      (`background_worker.py:275-291`), so `/jobs/{id}` polls
      `progress_value` that nothing writes
      (`app/routers/simulations.py:311-318`). Thread a
      `progress_callback(job_id)` through, or delete the plumbing.

### R2.3 🟡 Migration runner: unsafe semantics + broken script
- [x] `db.run_migrations()` runs on **every simulation job**
      (`background_tasks.py:113`) with no advisory lock, marks
      "already exists"-failures as applied, and `continue`s past genuine
      failures (`postgresql_db.py:326-357`). Run once, deploy-time
      (Cloud Run job / CI step), under `pg_advisory_lock`; failures abort.
- [x] `api/run_migrations.py:4` hardcodes
      `sys.path.insert(0, '/Users/oscarsverud/dev/btc_sim')` — a stale
      path from two repos ago. Fix.

### R2.4 🟡 Synchronous report rendering in the request path
- [x] `GET /simulations/{hash}/report` → `regenerate_ui_results` (~700
      lines) runs inline behind a 16-entry TTL cache
      (`app/routers/simulations.py:412-462`); N concurrent cache misses
      render N full reports, each holding a threadpool thread + DB
      connections. Add a per-hash single-flight lock, or route through the
      job queue like PDFs.

### R2.5 🟢 Misc
- [x] Naive-datetime staleness check in `check_simulation_cache`
      (`postgresql_db.py:961-974`) — breaks/misfires when server TZ ≠ DB
      column semantics (UTC on Cloud Run). Use `timestamptz` + UTC now, or
      compute age in SQL. Kill the bare `except:` at `:981`.
- [ ] `simulate-form.tsx:100-122`: infinite `for(;;)` poll with no
      AbortController — keeps polling after navigation, forever on
      persistent errors. (Fold into R5.6's shared hook.)

---

## R3 — Cloud Run deployment (W7 blockers)

**Topology:** three services — **web** (Next standalone, public), **api**
(`min-instances=1`, `--no-cpu-throttling` while LangGraph runs in-process),
**worker** as its own always-on service. *Not* the old sidecar `start.sh`
pattern — that's exactly what made the old worker CPU-throttle and die
silently. The SKIP-LOCKED DB queue is fine at this scale; no Cloud Tasks
migration needed once R2.1 lands. → This is what `deploy/` (merged W7
scaffolding) implements; remaining deltas are the open items below.

- [x] **R3.1 🔴 PDF storage** — landed on main (`8a2e289` +
      `758e8ae` failure-marking): worker saves via
      `get_pdf_storage().save_pdf(...)`, GCS init failures fatal, deploy
      sets `PDF_STORAGE_BACKEND=gcs`.
- [x] **R3.2 🔴 Worker deployability** — landed on main (`99c1000`):
      `worker.py` serves a `$PORT` health listener; deploy runs it as its
      own always-on service (`min/max-instances 1`, `--no-cpu-throttling`,
      `--no-allow-unauthenticated`).
- [ ] **R3.3 🔴→🟡 LangGraph runs in daemon threads in the API process**
      (`app/agents/runner.py:110-115`). *Mitigated* on main: deploy.sh
      runs api with `--no-cpu-throttling` + `min-instances=1` for exactly
      this reason (documented in the script + DEPLOY.md follow-ups).
      Remaining better-fix: route generation through the BACKGROUND_JOBS
      queue — the Postgres checkpointer already makes runs movable — which
      also lifts the unthrottled-api cost.
- [ ] **R3.4 🔴 SIGTERM grace**: worker checks its shutdown flag only
      *between* jobs (`background_worker.py:57`); a 20-min sim gets
      SIGKILLed and strands PROCESSING until stale cleanup. Set termination
      grace high (600s+) and pair with R2.1's heartbeat.
- [ ] **R3.5 🟡 Connection math**: api pool maxconn 20 **at import time**
      (`postgresql_db.py:177-187` via `db/database.py:5`) + LangGraph
      psycopg_pool (4) + worker pool + Next `pg` pool (10) × instances can
      blow a small Cloud SQL tier's `max_connections`. deploy.sh runs api
      at `--max-instances 10` with the default pool of 20 → 200+ potential
      api connections alone. Set `DB_POOL_MAX` 3-5 in the deploy env
      and/or cap api max-instances. (Socket connection already done.)
- [x] **R3.6 🟡 File logging** — LOG_TO_FILES=0 gates the file handlers (R4 logger rewrite); set it in deploy.sh: `RotatingFileHandler('simulation.log')` +
      `ui_interaction.log` (`logger.py:101-111`) → in-memory FS on Cloud
      Run, invisible to Cloud Logging. Env-gate to stdout-only in prod.
- [ ] **R3.7 🟡→🟢 Next.js**: `output: "standalone"` landed
      (`web/next.config.ts`); `API_URL` is injected at deploy time.
      Remaining: fail fast when `API_URL`/`INTERNAL_API_SECRET` are unset
      in prod instead of defaulting to localhost / silently sending `""`
      (`web/lib/api.ts:15,24`).
- [ ] **R3.8 🟡 SSE vs request timeout**: generation stream
      (`app/routers/strategies.py:503-563` + BFF proxy) can idle past the
      configured limit — deploy.sh sets api `--timeout 300`. Raise toward
      ~3600s on web+api (or accept cuts: the `after=seq` reconnect cursor
      makes them survivable — verify the client actually reconnects).
- [x] **R3.9 🟢** Landed via `deploy/` (W7): Cloud SQL socket, GCS env,
      Secret Manager `--set-secrets`, no sidecar, worker not public.
      Residual (tracked in DEPLOY.md follow-ups): api is
      `--allow-unauthenticated` and relies on the secret header — ingress/
      IAM hardening pending; old-repo DB password rotation → R1.6.
- [ ] **R3.10 🟢** Cold starts: mostly moot now with `min-instances=1`;
      optional `--cpu-boost`. Import-time pool creation still crash-loops
      if the DB is briefly unreachable at boot.

---

## R4 — Deletion pass (~3-4k lines, no behavior change)

> **Status 2026-09-14:** MERGED to main (net −3,919 lines, 9 commits,
> reviewed with a liveness sweep + behavior-preservation pass, both
> clean). Bonus closures: R5.1's nested-connection hazard (fork count
> inlined on the save transaction), R3.6 (LOG_TO_FILES=0 for Cloud Run).
> Latent bugs surfaced and repaired: perf/memory/slow-query config flags
> never actually read config.yml; update_cached_simulation_params was a
> silent no-op all PG era; limits/user_profile only worked via the regex
> cursor wrapper. Leftovers for later: inert GCP_MONITORING_* env vars in
> deploy.sh; pre-existing dead core/db_logger.py.

- [x] 🟡 Dead half of `background_tasks.py` (1,864 lines): zero-caller
      Streamlit-era entry points `run_simulation_process` (:42),
      `on_simulation_complete` (:70), `regenerate_ui_thread` (:463),
      `_truly_lightweight_debug_process` (:1203),
      `generate_pdf_from_ui_data_process` (:1252), `pdf_worker_process`
      (:1439), `run_strategy_evaluation_process` (:1792) + their
      queue/process plumbing. Live: `run_and_save_simulation`,
      `regenerate_ui_results`, `_generate_pdf_for_simulation` — give them
      proper modules.
- [x] 🟡 `services/git_service.py` (496 lines) GitHub-as-strategy-store +
      the git branches of `save_custom_strategy` and `builtin_sync`: the
      DB is authoritative (`postgresql_db.py:1433-1435` says so), every
      call site is try/except-and-continue. Keep
      `calculate_strategy_hash` as the identity mechanism.
- [x] 🟡 Multi-backend DB abstraction: `db/database_interface.py` (one
      impl, drifted signatures), `Dialect`/factory branches,
      `SQLiteQueries` entries for nonexistent tables (`db/queries.py`),
      and the `PostgreSQLCursor`/`Connection` regex-translation wrappers
      (`postgresql_db.py:69-155`). One plain class, native `%(param)s`.
- [x] 🟡 `monitoring/cloud_monitoring.py`: imports nonexistent
      `core.config_manager` → permanently self-disabled (`:33-40`); every
      connection checkout pays a wasted hook (`postgresql_db.py:228-239`,
      which itself has a `NameError` on `os` swallowed since day one).
      Delete both; use Cloud Run built-in metrics first.
- [x] 🟢 Dead reporting: `reporting/plotting.py` (0 bytes),
      `metric_glossary.py`, `thumbnail_gauge.py`,
      `plot_simulation_overview_interactive_old`
      (`interactive_plotting.py:975`), `get_plotly_dark_theme_template`,
      `_create_settings_table_old` + deprecated block in `pdf.py`,
      unused `executive_visuals` builders.
- [x] 🟢 Dead app-layer bits: duplicate shadowed `get_leaderboard`
      (`postgresql_db.py:2059` vs `:2301` — first would `AttributeError`
      if unshadowed), unreachable block in `get_or_create_user_id`
      (`:526-530`), dead `require_user` in `deps.py:45-48` + three private
      copies, stray `api/assets/logger.py`, Streamlit noise in
      `logger.py:44-51`.
- [x] 🟢 Branding scrub: PDF footer still says MyMonteCarlo
      (`reporting/pdf.py:693`); Streamlit references in
      `background_tasks.py:1-9`, `utils/performance.py:280-309`,
      `core/currency_config_example.py:24`.

---

## R5 — Architecture refactors

> **Status 2026-09-15:** R5.2a, R5.3-R5.8 merged to main (five reviewed
> branches; browser-verified on an integration build). Review catches
> fixed pre-merge: getViewer was swallowing Next's dynamic-rendering
> signal (static logged-out prerender risk); degraded /me fallbacks now
> fail loud on auth-branching pages; job-poll failure cutoff widened to
> ~60s with backoff. Note: the cn package swap turned out to be pure
> supply-chain hygiene — the old package already had merge semantics.
> Remaining in R5: R5.2b (postgresql_db domain split — needs its own
> design pass), R5.9 (chart-theme single source), R5.10 (engine
> relocations + the **=/// = regex rewriter).

- [x] **R5.1 🔴 `save_custom_strategy` layering inversion** — closed by R4's git excision (plain transactional upsert; fork count inlined on the same cursor)
      (`postgresql_db.py:1243-1556`, 314 lines): db→services import, GitHub
      network I/O inside an open transaction, nested pool checkout via
      `increment_fork_count` (:1516) = pool-exhaustion deadlock pattern.
      Mostly dissolves with R4's git_service removal; the remainder becomes
      a plain transactional upsert. Do first — it's the concurrency risk.
- [x] **R5.2 🟡 `postgresql_db.py` (3,028 lines) split** — two stages:
      (a) a `@contextmanager` for connection/cursor/commit-rollback
      (~70 copies of the boilerplate, ~1,000 lines removed mechanically);
      (b) split into per-domain modules (users / simulations / strategies /
      jobs / leaderboard) sharing the pool. Let exceptions propagate —
      today failures collapse to `None`/`[]`/`False` (e.g. `:417-420`,
      `:1075-1076`) so callers can't tell "empty" from "DB down".
- [x] **R5.3 🟡 Restore real `cn`**: `web/lib/utils.ts:1` re-exports the
      8-year-old npm package `cn` (no tailwind-merge → conflicting utility
      classes resolve by CSS source order; unvetted micro-dep). Restore
      `clsx` + `tailwind-merge`; drop `cn`, move `shadcn` CLI out of
      runtime deps (`package.json`).
- [x] **R5.4 🟡 Shared evaluation-results component**: radar + score grid
      + scenario table duplicated (`leaderboard/entry-card.tsx:176-252` vs
      `strategies/[id]/evaluation-tab.tsx:183-245`); `categoryLabel` ×4.
- [x] **R5.5 🟡 One `usePdfDownload` hook**: the 120×2s generate-and-poll
      loop is duplicated character-for-character
      (`pdf-button.tsx:10-38`, `simulation-card.tsx:66-94`).
- [x] **R5.6 🟡 One `useJobPolling` hook** (or adopt TanStack Query):
      four hand-rolled polling patterns; model on evaluation-tab's
      teardown-safe one; fixes R2.5's leak.
- [x] **R5.7 🟡 Error/loading story**: no `error.tsx`/`loading.tsx`
      anywhere; `getViewer()` throws site-wide when the API is down
      (`web/lib/api.ts:76-78`) — even the guest landing crashes. Root
      `error.tsx`, `loading.tsx` for the serial-fetch dashboard, degrade
      `getViewer` to anonymous for public pages.
- [x] **R5.8 🟢** Shared `<SignInGate>` (five bespoke copies, already
      drifting); standardize all BFF routes on `proxyJson` (12 hand-rolled
      copies throw 500 on upstream non-JSON); type `Strategy` in
      `strategies/model.ts` instead of `Record<string, any>`
      (`strategy-detail.tsx:37-38`).
- [ ] **R5.9 🟢 Single source of truth for chart theme**: web mirrors
      `color_scheme.py` hex-by-hex (`web/lib/chart-theme.ts:7-20`), which
      itself encodes light/dark four parallel times; two conflicting plotly
      base layouts. Serve palette from `/config` or codegen the TS.
- [ ] **R5.10 🟢** Move `sandbox_tester.plot_test_results` (plotly in
      `core/`, `sandbox_tester.py:245-403`) into `reporting/`, reusing the
      interactive builders. Move `api/simulation.py` under `core/`
      (legit entry point, wrong altitude). Fix theme-at-import side effect
      (`interactive_plotting.py:19` → YAML I/O at import,
      `color_scheme.py:366-418`). Fix the `**=`/`//=`-corrupting regex
      rewriter (`sandbox.py:364-409`) as an AST transform; drop the naive
      `"import os" in code` string check (`sandbox.py:429`).

---

## R6 — Performance (COGS lever, not urgent)

- [ ] 🟡 `prepare_results_dataframe` builds one DataFrame **per
      simulation** then a 10,000-column concat
      (`core/shared_logic.py:148-173`). Preallocate a
      `(num_sims, num_years, num_metrics)` array (fixed schema), build the
      MultiIndex frame once.
- [ ] 🟡 Per-path Python loops in `calculate_final_statistics`:
      `npf.irr` per path (`core/stats.py:300-317`), per-column drawdown/
      ulcer/psych loops (`:389-443`). Vectorize column-wise; consider a
      cheaper IRR proxy.
- [ ] 🟢 Draw the whole scenario matrix in one RNG call instead of a
      10k-iteration loop (`simulation.py:65-78`); use a
      `np.random.Generator` instead of global state (also `core/data.py:182`).
- [ ] 🟢 Per-instance `@ttl_cache` on home/leaderboard/report
      (`app/routers/home.py:84,364`, `simulations.py:412`) — fine at this
      scale, but per-process: instances pay regeneration separately and can
      serve different snapshots. Known behavior; one more reason to keep
      api max-instances small.

---

## Verified healthy (no action)

- BFF integrity: no client fetch to FastAPI; secret under `server-only`;
  no `NEXT_PUBLIC_` leak; `.env` files untracked.
- All 7 routers behind router-level `verify_internal_secret`; only
  `/`+`/healthz` open (intentional).
- Job claiming: atomic `UPDATE … FOR UPDATE SKIP LOCKED`
  (`postgresql_db.py:2664-2680`); idempotency keys; `ON CONFLICT DO
  NOTHING` on the create-sim race; retry backoff.
- W5 runner: checkpointed graph, atomic `claim_run`, orphan reconcile at
  startup, backed-off SSE tail.
- `drop_all_tables` behind tier + secret + `ADMIN_PASSWORD` + confirmation
  text.
- PDF path renders plotly→PNG→reportlab; no matplotlib chart duplication.
- Better Auth sessions in Postgres (multi-instance safe); AI credits/tier
  limits DB-backed.
- Migrations correctly *not* run at api startup (startup = idempotent
  builtin sync + orphan reconcile only).
