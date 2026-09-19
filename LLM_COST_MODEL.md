# LLM cost model

What one AI operation costs us, what we should charge for it, and how much
the free tier may burn. Written 2026-09-19 alongside the LLM usage logging
(`LLM_USAGE`, `/admin/llm-usage`); the per-operation numbers below are
**estimates** until that page has ~20 real runs per operation — then replace
them with its medians and re-derive the credit prices (a 5-minute job, see
§5).

Assumptions used throughout: USD/SEK 9.8 (2026-09-19); Gemini list prices as
of 2026-09-19 (`api/core/llm_pricing.py`); thinking tokens billed as output.

## 1. What an operation costs today

Prompt sizes are measured from the real graph (fake-LLM run, so `generate` /
`static_review` / `analyze` prompts are bumped ~1k tokens for real strategy
code, which is 4–8k chars vs the 1.3k stub). Output and *thinking* tokens are
assumptions — thinking is the single biggest unknown and typically dominates
the bill on Flash.

Default models: strong = `gemini-3.8-flash` ($0.75 / $3.75 per 1M in/out,
promo until 2026-12-31), fast = `gemini-3.5-flash-lite` ($0.30 / $2.50).

### Strategy creation (happy path: 5 calls, no clarify / rework / refine)

| step | tier | in | out | thinking | cost |
|---|---|---:|---:|---:|---:|
| extract_spec | fast | 300 | 500 | 300 | $0.002 |
| plan | strong | 5,300 | 1,200 | 2,500 | $0.018 |
| generate | strong | 7,500 | 2,500 | 4,000 | $0.030 |
| static_review | fast | 1,500 | 300 | 300 | $0.002 |
| analyze | strong | 2,800 | 700 | 1,500 | $0.010 |
| **total** | | 17.4k | 5.2k | 8.6k | **≈ $0.062** |

- One rework round (generate → static_review → analyze again) ≈ +$0.042;
  one review "request changes" round ≈ +$0.055; clarify ≈ +$0.002.
- Realistic mean with ~30% of runs reworking once and ~20% refining once:
  **≈ $0.085 per creation**. Hard upper bound (`MAX_LLM_CALLS = 30`):
  ≈ $0.40.
- The fast tier is ~7% of the run. Swapping it (e.g. to GPT-5.6 Luna) saves
  cents; the strong tier is where model choice matters.

### Strategy evolution (in-place edit of a seed)

Smaller prompts (no example retrieval, edit-list plan) and smaller outputs:
**≈ $0.04 happy path, ≈ $0.05 mean** (strong ≈ $0.036, fast ≈ $0.003).

### Strategy Q&A (per question; `feature/strategy-qa`: triage fast + answer strong)

Triage ≈ 3k in / tiny out ≈ $0.002; answer ≈ 9k in (code + spec + trace +
history) / 700 out / ~2k thinking ≈ $0.017 → **≈ $0.02 per question**.

### Simulation-report AI analysis (2 fast calls)

Analysis + executive summary, ≈ 3.5k in each, 900 + 500 out, ~800 thinking
each → **≈ $0.01 per report**.

### Sensitivity

| scenario | creation (mean) | evolution | question | report |
|---|---:|---:|---:|---:|
| today (Flash promo) | $0.085 | $0.05 | $0.02 | $0.010 |
| from 2027-01-01 (3.8 Flash ×2) | $0.16 | $0.09 | $0.03 | $0.010 |
| strong = `gemini-3.1-pro-preview` ($2 / $12) | $0.26 | $0.13 | $0.05 | $0.010 |
| thinking 2× the assumption | $0.13 | $0.08 | $0.03 | $0.015 |

⚠ The local `api/.env` sets `GEMINI_MODEL_STRONG=gemini-3.1-pro-preview`
— the Pro row, ~3× the default. Whatever production runs must be known
before pricing is fixed; `/admin/llm-usage` shows the model per call.

## 2. What the current limits imply

Today's gate (`core/limits.py`) counts *generations*, not cost:
FREE = 10 / month, PRO = 50 / month, every strategy run or AI report = 1.

| | FREE (10 gens) | PRO (50 gens) | PRO price | LLM cost share of price |
|---|---:|---:|---:|---:|
| Flash promo | $0.85 / mo | $4.3 / mo | $10.1 | 42% |
| Flash from Jan 2027 | $1.6 / mo | $8.0 / mo | $10.1 | 79% |
| `gemini-3.1-pro-preview` | $2.6 / mo | $13 / mo | $10.1 | **129% — loses money** |

(worst case = allowance fully used on creations; a mix with evolves /
questions / reports is cheaper, but the gate can't tell them apart.)

So: the PRO allowance is already above the 1/3 target on the promo price,
and negative on Pro. The free tier at 10 creations/month costs 8–25× what
§4 recommends. Neither is a problem at beta scale (tens of users); both are
at hundreds.

## 3. Pricing principle: charge 3× LLM cost

Equivalently: **a tier's monthly LLM budget = ⅓ of its price.** Denominate
that budget in credits where **1 credit = $0.01 of LLM list cost**, so the
credit is a stable unit that survives model swaps and reprices.

| tier | price | ⅓ budget | credits / month |
|---|---:|---:|---:|
| PRO | 99 SEK ≈ $10.1 | $3.37 | **300** (≈30%, the rest is headroom for retries and price drift) |
| WHITELABEL (placeholder) | 999 SEK | $34 | 3,000 |
| FREE | 0 | — | see §4 |

Charge a **fixed credit price per operation type**, not the measured cost of
each run: users need to know what a creation costs before they start, and
rework loops are ours, not theirs. The price list is `ceil(p75 measured
cost, in cents)` — the p75 (not median) absorbs rework/refine variance so
the 3× holds on average:

| operation | est. p75 today | **credits** | PRO 300 buys… |
|---|---:|---:|---|
| strategy creation | $0.10 | **10** | 30 creations, or |
| strategy evolution | $0.05 | **5** | 12 creations + 15 evolves + 40 questions + 25 reports |
| strategy question | $0.02 | **2** | |
| report AI analysis | $0.01 | **1** | |

Charging rules:
- Reserve the credits when the operation starts (gate = `used + price ≤
  budget`), settle at the end. Refund on *system* failure (LLM outage, budget
  exhausted, crash); no refund when the user discards the result — the cost
  was incurred.
- Clarify answers and review refinements happen inside one run and are
  covered by its price; a refine loop that goes to the `MAX_REVISIONS` cap
  is still one creation.
- `AI_CREDIT_USAGE.credits_used` already exists as a monthly counter;
  incrementing it by the operation's price instead of `1` and reading the
  budget from the tier is the whole gating change. `LLM_USAGE` stays the
  actual-cost ledger, so *charged vs actual* per user is one query (the
  admin page should show it once credits exist).

## 4. How much may the free tier use?

The free tier is marketing spend; size it like CAC, not like a feature.
With PRO gross margin ≈ 66 SEK/month after LLM cost and, say, 6 months
retention, a converted user is worth ≈ 400 SEK ≈ $40. At a 4% free→PRO
conversion that's ≈ $1.6 of allowable *lifetime* LLM spend per free user at
break-even — so the target is well under $1 per free user, total, not per
month.

Recommendation:

| | credits | ≈ LLM cost | what it buys |
|---|---:|---:|---|
| signup grant (once) | **40** | $0.40 (≈ 4 SEK) | 2 creations + 2 evolves + 5 questions + a few reports — the whole loop, twice |
| monthly refill | **10** | $0.10 (≈ 1 SEK) | one evolve, or 5 questions, or 10 report analyses |

Why this shape: the one-time grant lets a new user actually build and
evolve a strategy (the moment that sells the product); the small refill
keeps dormant free accounts nearly free (10 credits × 1,000 users = $100/mo
*worst case*, real utilisation is a fraction) and makes "I want to build
another one" the upgrade prompt. A monthly 10-creation allowance, by
contrast, is $0.85–2.6 per active free user per month forever.

Sanity rule: **free-tier LLM spend should stay under ~30% of MRR.** The
admin page's per-tier totals make this a glance.

### Don't-go-broke table (worst case = every user spends their full allowance)

Monthly LLM cost. "Proposed" = the caps above; because credits are
cost-denominated, that column holds at any model price *as long as the
credit prices are re-derived* — the two "stale" columns show what happens
if they are not (users keep getting the same number of operations while
each one costs more).

| users (free / PRO) | MRR | proposed | proposed, prices stale after Flash ×2 | proposed, stale + Pro-preview | **today's rules (Flash promo)** |
|---|---:|---:|---:|---:|---:|
| 100 / 10 | $101 | $43 | $81 | $132 | $128 |
| 1,000 / 50 | $505 | $280 | $527 | $857 | **$1,060 (loss)** |
| 5,000 / 100 | $1,010 | $950 | $1,790 | $2,910 | **$4,680 (loss)** |

(free = 10 credits/mo + 40 once, amortised ≈ 13/mo = $0.13; PRO = 300
credits = $3.00.) Typical utilisation is 20–30% of worst case, but the rules
must survive the worst case. Reading it: with re-derived prices, total
worst-case spend is 43% / 55% / 94% of MRR down the rows, and the free
share alone is 13% / 26% / 64% — the 5k-free row breaks the 30% rule, so
by then the refill shrinks or conversion has to beat 2%. Today's rules lose
money from ~1,000 free users on. The Pro model as strong tier is only
viable with Pro-specific credit prices (×3) or reserved for PRO users.

## 5. Operating it

- **Monthly (5 min):** open `/admin/llm-usage`, window 100 → take each
  operation's p90 (shown) or p75, `ceil(cents)` → update the credit price
  list. Watch the "unpriced calls" warning after any model change.
- **Alerts worth adding:** last-7-day spend > 2× the previous week; any
  single user > 3× the PRO budget in a month (abuse); a free user hitting
  the cap 3 months running (upgrade nudge).
- **2027-01-01:** 3.8 Flash doubles. Either re-derive prices (PRO gets ~15
  creations instead of 30) or move the strong tier. The price table in
  `llm_pricing.py` flips automatically; the credit prices don't.
- **Retries are ours.** The rework loop (up to 3) and refine loop (up to 3)
  are bounded by `MAX_LLM_CALLS = 30`; a run that hits the cap costs ≈
  $0.40 and is charged 10 credits — that's why prices use p75, and why the
  admin step table exists (to see whether a prompt change moved the mean).

## 6. Implementation plan (next branch, once the numbers are real)

1. `tier_config/tiers.py`: `ai_credits_monthly` (300 / 10) + `ai_credits_signup` (40) replace `ai_generation_credits_monthly`; `core/llm_credits.py` holds the operation price list.
2. `core/limits.py`: `reserve_credits(user, operation)` / `settle` / `refund`; monthly counter stays in `AI_CREDIT_USAGE`; signup grant as a one-time row.
3. Gate the four entry points: `POST /strategies/generate` (create + evolve), the Q&A `POST /qa/messages`, and the report-analysis flag in `POST /simulations`.
4. Web: credits remaining in the designer's start card and in Settings; admin: charged-vs-actual column on `/admin/llm-usage/users/[id]`.
5. Migrate existing users: FREE gets the signup grant on first login after deploy.
