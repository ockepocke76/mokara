# Streamlit → Mokara parity report (2026-09-08)

Page-by-page audit of the old Streamlit app (code + UI) against the new app,
after the full parity sweep. **Everything functional has been ported except
where listed under "Remaining differences"** — each remaining item has a
motivation. Strategies (W5) is excluded by decision.

## What the sweep added (was missing before it)

- **Landing/Home rebuilt to the old `pages/0_Dashboard.py` composition** via a
  new `GET /home` payload:
  - Guest: the real hero ("Design Better Investment Strategies, Backed by
    Data 🎯"), three-pillar USP, beta status box + Browse/Login CTAs,
    **Featured Strategies with mini radar charts**, How It Works, and all 8
    educational sections (passive-investing deep dive ported verbatim, stress
    test spotlight + evaluation-info expanders, excellence-score spotlight,
    investor-profile spotlight, Community Pulse, Asset Class Showdown,
    Did You Know, Terms of the Day).
  - Logged-in: welcome + stats + Quick Actions + **recent simulations as
    preview cards with the two mini charts** + Featured Strategies +
    collapsed Knowledge Base.
- **Simulation preview cards** (`GET /simulations/{hash}/preview`): Portfolio
  Value (median path + IQR) and Yearly Cash Flow mini-Plotly charts, category
  badge, category-specific quick stats — used on Home and as a "📊 Preview"
  expander on every My Simulations card (port of
  `ui/simulation_preview_card.py`).
- **Assets page is interactive again** (`/docs/assets`): asset selector,
  ticker/description, parameter readout with tooltips, and the **historical
  price chart** per asset (`GET /assets`, `GET /assets/{key}/figure`).
- **Methodology flowchart**: the detailed Mermaid simulation flowchart now
  renders in `/docs/methodology` (`GET /methodology/flowchart` + client-side
  mermaid).
- **About page completed**: The Three Pillars, Who We Are (Stockholm/lagom),
  Resources & Tools, Get in Touch / Join Us / Early Access roadmap.
- Mobile header fix (logo-only below 480px).

## Page-by-page status

| Page | Status |
|---|---|
| Landing (guest) | ✅ full parity |
| Home (logged-in) | ✅ full parity |
| Run Simulation | ✅ parity (see D1) |
| Results report | ✅ item-stream parity, 13 charts (see D2, D3) |
| My Simulations | ✅ parity + preview expander (see D4; Compare dropped by decision) |
| Leaderboard | ✅ full parity after 2026-09-08 redesign (category-scoped model: audience-framed category selector w/ Withdrawal default, cascading per-category profiles defaulting to the balanced variant, profile-weighted rankings + note, entries w/ source badges, description, medal-colored weight-marked radar, category+profile-filtered Component Scores grid, per-scenario table, Clone CTA w/ in-library state, usage badges, creator shown to logged-in only; Load More pagination; per-category Weighting Profiles w/ weight bars; Scenario Performance Heatmap; per-category How Evaluation Works; Try These CTAs) |
| Assets | ✅ parity (see D5) |
| Methodology | ✅ parity incl. flowchart |
| Glossary / Disclaimer | ✅ verbatim (generated from the same engine functions) |
| About | ✅ parity |
| Settings | ✅ parity (profile, currency, public username + 🎲) |
| Admin | ✅ ported in W6 (users/tiers/allowlist, jobs, evaluations, migrations, reset) |
| Strategies | ⏸ W5 placeholder (agentic redesign, separate track) |

## Remaining differences — and why

**D1 — Results open on their own page, not inline under Run Simulation.**
The old app rendered results inline because Streamlit had no routing. The new
app navigates to `/simulations/{hash}` on completion. Motivation: reports get
a stable, shareable, reloadable URL; identical content (the full report).

**D2 — No Table of Contents expander at the top of the report.** The old TOC
was anchor links into a long scroll. The new report's chapter accordions ARE
the table of contents (all section titles visible at once, click to open).
Adding a separate TOC would duplicate the accordion list.

**D3 — Some report charts lack the old in-chart toggle menus.** The old UI
*re-applied* Plotly `updatemenus` (e.g. nominal/real switches on the
Distribution and Price History charts) after loading cached figures, because
the cached figures lost them. The new report renders the engine's figures
as-is, so charts that carry their menus keep them; the re-application step
for the handful of cached-figure cases was not ported. Motivation: small
cosmetic-interactive delta, and the right long-term fix is in the engine
(emit figures with menus attached) rather than patching in the UI. Can be
added on request.

**D4 — "View" on My Simulations links to the report page instead of
expanding inline.** Same rationale as D1; the preview expander covers the
quick-look case, the report page covers the full view.

**D5 — Assets lives under `/docs/assets` instead of a top-level nav item.**
The old app had 11 flat nav entries; the new app groups content pages under
Docs (About, Methodology, Assets, Glossary, Disclaimer) to keep the header
sane. All content is one click deeper at most.

**D6 — Login is a page, not an inline Google button in the hero.** Better
Auth (the new auth stack) handles OAuth on `/login`; the hero's Login CTA
links there. One extra click for guests; in exchange the app gets real
sessions/cookies (which the old app had disabled entirely). Note: Google
login itself still needs the redirect URI registered in the Google console —
env setup, not code.

**D7 — "Sample Simulation Results" on the guest landing is empty locally.**
The section is implemented and renders demo simulations when the database
has public/demo sims (`get_user_simulations(None)`), exactly like the old
app — the local DB simply has none marked as demos. Same emptiness in the
old app locally. Prod seed data will light it up.

**D8 — Old mobile bottom-nav replaced by a hamburger sheet menu.** The old
bottom nav was a workaround stack (`mobile_nav*.py`, device detection); the
new app is properly responsive. Deliberate improvement, agreed in WV.

**D9 — Preview mini-charts use the light chart theme.** The old preview
cards hardcoded `theme='dark'` (dark plots on a light page). The new ones
pass `theme='light'` for visual coherence with the rest of the app.

**D10 — Sidebar login/profile panel not reproduced.** The old desktop
sidebar had an auth widget; the new app has the header user menu instead.
Same capabilities (sign in/out, settings), different placement.

## Not ported anywhere (dead by design)

Compare tab (decision 2026-09-06); Streamlit machinery (session-state
registry, fragments/rerun polling, cookies-manager and its version pin,
theme-sync script); the separate `admin_app.py` deployment.
