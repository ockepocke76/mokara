# CLAUDE.md

Guidance for Claude Code and developers working in this repository.
(Workflow rules adopted from the linyfy project — learned the hard way there;
keep them the same way here.)

## Workflow

- **Isolate parallel work in a worktree.** When starting a new feature or a
  distinct line of work — especially if other Claude sessions may be running —
  use a worktree (EnterWorktree) instead of coding on the shared branch
  (worktrees live under `.claude/worktrees/`, which is gitignored). Sequential,
  single-session work can use a normal feature branch.
- **Commit in focused, single-theme groups** — stage precise paths per commit.
  **Never `git add -A` in this repo**: it has bitten twice already (an embedded
  worktree repo under `.claude/`, generated PDFs under `api/pdf_cache/`).

### Branch & commit hygiene
- **One branch = one theme.** Name the branch after the work it contains
  (`feature/w5-agentic-strategies`, `fix/leaderboard-cascade`) and keep it to
  that theme. If the work shifts theme, branch again.
- **Commit messages must match the diff.** If you're tempted to write "and",
  split the commit (stage precise paths).
- **NEVER merge to `main` without an explicit go-ahead from Oscar in the
  session.** Finished work waits on its feature branch — reviewed, tested,
  presented — until he says "merge it" (or equivalent). Work often has a
  pending human check (a visual verdict, a side-by-side against the old app)
  that the code can't see.
- **Review before merging to `main` — always, unprompted.** Before any merge
  into `main`, run a code review of the branch diff (the `/code-review` skill)
  and act on it: fix confirmed findings, surface anything unresolved instead
  of merging silently. Only an explicit "skip the review" waives it. Scale
  effort to the diff.
- **Land approved branches on `main` promptly, then delete them** (local *and*
  origin). Before deleting, confirm the branch isn't checked out in another
  worktree (`git worktree list`).
- **No force-push to shared/pushed branches.** Fix history going forward.
- Transition note: through the initial build (W0–WV) work was committed
  directly to `main` with Oscar's per-step approval. From here on, new work
  goes on feature branches under the rules above.

### Never commit
- **Secrets — ever.** This repo exists because the predecessor's history
  leaked credentials. `.env` stays gitignored; commit `.env.example` updates
  only. No keys, tokens, passwords, or DB dumps.
- Build artifacts and dependencies: `node_modules/`, `web/.next/`,
  `api/.venv/`, `api/pdf_cache/`, `output/`, `.claude/` (all gitignored —
  never force-add them).

## Definition of done (per change)
- `cd api && .venv/bin/python -m pytest tests/` green (needs local Postgres
  `btc_simulator_local`); the no-streamlit guardrail test must stay passing.
- `cd web && npm run lint && npm run build` clean.
- **User-visible changes are verified in the browser** (dev servers via the
  session's `mokara-api`/`mokara-web` launch entries, ports 8000/3100; jobs
  need `api/worker.py` running) — never hand the user an unverified page.
- Porting/parity work: check the change against the old Streamlit app
  (`~/dev/mymontecarlo`, reference-only) and **understand the old design's
  intent before reimplementing it** — see PARITY_REPORT.md for the standing
  differences (D1–D10) and their motivations.

## Architecture ground rules
- **BFF pattern**: the browser only talks to Next.js; FastAPI is internal.
  Every new API endpoint goes behind the `verify_internal_secret` dependency,
  and the web app reaches it through `lib/api.ts` / an `/api/bff/*` route —
  never `fetch` FastAPI from client code.
- **The engine (`api/core|db|services|utils|reporting`) stays framework-free**
  — no FastAPI imports inside it, no streamlit ever (guardrail-enforced).
  App-layer logic lives in `api/app/`.
- Engine behavior changes must keep the copied test suite green; if a change
  is really an engine bug fix, note it in the commit (the old repo is frozen —
  fixes land here only).

## Where to start
- **[PORT_PLAN.md](PORT_PLAN.md)** — architecture, decisions log, and the
  wave-by-wave tracker (W0–W7 + WV). Update its checkboxes and progress log
  as work lands.
- **[PARITY_REPORT.md](PARITY_REPORT.md)** — Streamlit-parity status per page
  and the accepted remaining differences.
- **[README.md](README.md)** — local run recipe (api + worker + web).
- `W5_DESIGNER_UX.md` — UX spec for the agentic strategy designer (W5).
- `LLM_COST_MODEL.md` — what an AI operation costs, the credit/pricing
  model, and the free-tier budget; `/admin/llm-usage` is the live view.
