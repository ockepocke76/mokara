# W5 Strategy Designer — UX specification

Companion to PORT_PLAN.md § W5. That section owns the agent graph; this file
owns everything the user sees. Written 2026-09-06 (design session w/ Claude).

**The core bet:** the pedagogic value is not "watch an AI work" — it's that
the finished page reads as an *explanation of how your strategy was built and
why you can trust it*. The UI is a build log that becomes a document.

---

## 1. Principles

1. **Narrative, not spinner.** Every graph stage produces a visible artifact
   the user can read. The page accumulates these top-to-bottom; when the run
   ends, scrolling the page = understanding the strategy.
2. **Plain language first, code second.** Most users won't read Python. The
   *blueprint* (numbered plain-language rules) is the primary artifact; code
   is collapsed "for the curious". The explanation ("in a crash year it…")
   outranks the stats.
3. **Progressive disclosure.** Every card has a one-line headline a
   non-programmer understands; details (tracebacks, raw stats, code diffs)
   live behind expanders. Nothing technical is *hidden*, nothing technical
   is *forced*.
4. **Honest uncertainty.** The test sim is 10 paths — say so, visibly:
   "a quick smoke test, not a verdict — run the full evaluation after
   saving." Never let the quick numbers look like a promise. Descriptive,
   never advisory copy ("the strategy withdrew X", not "you should…").
5. **The user is the editor, not the audience.** Assumptions are always
   shown as changeable; the review step is a real decision point with real
   alternatives, not an OK button.
6. **No surprise costs.** Credit price shown before start; per-run metering
   means the number on the button is the number charged, regardless of
   internal retries.

## 2. Flow shape

One page: `/strategies/new` (and `/strategies/[id]/evolve` — same page,
seeded). Two zones:

- **Stage rail** (left on desktop, horizontal progress bar on mobile):
  the graph stages with human names and states
  (pending · active · done · needs-you · failed):

  | Rail label | Graph node(s) |
  |---|---|
  | Understanding | extract_spec, clarify |
  | Studying examples | retrieve |
  | Blueprint | plan |
  | Writing code | generate, rework |
  | Safety checks | validate, static_review |
  | Test flight | test_sim + baseline |
  | Behavior review | analyze |
  | Your decision | review interrupt |

- **Build log** (main column): one card per stage, appended as events
  stream in. Completed cards collapse to their headline + key artifact;
  the active card shows live micro-status ("Running test simulations —
  path 7/10"). Clicking a rail stage scrolls to its card.

Rework loops do NOT add new stages — the affected card shows
"Attempt 2 of 3 — fixing: *used a forbidden operation*" with the failed
attempt tucked into an expander. The rail never moves backwards; retries
are progress, not regression.

## 3. Screens & cards

### 3.0 Entry
- Big prompt textarea + strategy name field (auto-suggested after spec,
  editable).
- **Three starter cards** = the built-ins' `get_user_prompt_template()`
  text, clickable to prefill ("Trinity-style 4% rule", "Buy-Borrow-Die",
  "Get Rich, Stay Rich"). Doubles as teaching-by-example: this is what a
  good prompt looks like.
- Short inline hint list: "Good prompts mention: your goal (retire /
  accumulate), when to sell or borrow, what to do in a crash."
- Footer of the submit button: `Generate — 1 AI credit (you have 7)`.
- Evolve entry adds a "Based on: <name>" chip + the seed's description.

### 3.1 Understanding (spec card)
Headline: **"Here's what I understood."** Rendered as sentences + chips,
not JSON:
- Goal / category badge (Withdrawal · Contribution · Hybrid) — with a
  glossary tooltip (link into the existing `/docs` glossary — reuse it for
  every term chip throughout the designer).
- Mechanics as a bullet list in the user's own vocabulary.
- **Assumptions visually distinct** (dashed border + "assumed" tag):
  "Assumed: withdrawals adjust for inflation — didn't say otherwise."
- Proposed parameters preview: name, default, range, one-line meaning.

If clarify fires: the card ends in an inline question form (radio options
+ free text, max ~3 questions), with **"Proceed with my assumptions"**
always present as a first-class button, not an escape hatch. One round max.

### 3.2 Studying examples
Small card, honest and quick: "Drawing on 2 similar strategies:" with mini
cards (name, category, leaderboard score badge, link). If nothing similar:
"No close matches — building from the base playbook." This is the
transparency artifact; keep it light.

### 3.3 Blueprint
**The pedagogic centerpiece.** Numbered plain-language rules:

> **Each year this strategy will:**
> 1. Check portfolio value against the starting value, inflation-adjusted.
> 2. Withdraw 4%, but cut to 3% if last year's return was negative.
> 3. Never sell during the first 2 years of a drawdown — borrow instead.

Rendered from the plan node's output. This is what the static-review and
analyze stages verify *against*, and the UI should say so later ("checked
the code against this blueprint — all 3 rules implemented ✓").

### 3.4 Writing code
Headline + strategy description. Code block **collapsed by default**
("View the Python — 84 lines"), syntax highlighted. Evolve mode: diff view
against the seed (changed lines highlighted) instead of a plain block.
Parameters table (final, matching `parameters`).

### 3.5 Safety checks
A literal checklist, ticking live:
- ✓ Compiles in the sandbox (untrusted-code jail)
- ✓ Dry run — all required methods behave
- ✓ Code implements the blueprint (rule-by-rule, from static_review)

On a rework: the failed line turns into "✗ → fixing (attempt 2 of 3)"
with a one-line human reason; full error/traceback in an expander. When
the run ultimately succeeds, failed attempts stay visible but collapsed —
honesty builds trust, and it shows the safety net working.

### 3.6 Test flight
Framed explicitly: **"Quick smoke test — 10 simulated markets × 30 years.
This checks behavior, not performance."**
- Small percentile fan chart (existing `components/chart.tsx`).
- Stat tiles: success rate, median final net worth, worst path, max
  drawdown — each with a glossary tooltip.
- **Paired baseline strip**: "On the exact same 10 markets, plain
  buy-and-hold scored: …" shown as a comparison row, with the caveat
  badge "10 paths = noisy; the full evaluation (8 scenarios) is the fair
  test." Never a green/red verdict color on the delta — neutral
  presentation, per the Goodhart rule.

### 3.7 Behavior review
The analyze node's narrative, structured:
- **"In a typical year:"** one paragraph.
- **"In the worst test path (crash of −38% in year 6):"** concrete
  walkthrough with real numbers from the traces — this single concrete
  story teaches more than every chart above it.
- **Blueprint conformance:** "All 3 rules observed in the test runs ✓"
  (or: "Rule 2 never triggered in these 10 paths — not proof it's broken,
  the test just didn't hit that condition." Honest uncertainty again.)

### 3.8 Your decision (review interrupt)
Sticky action bar once analyze completes:
- **Save strategy** (primary) → save node → success screen with next
  steps: "Run the full 8-scenario evaluation" (primary suggestion),
  "Test with your own settings", "Publish to leaderboard".
- **Request changes** → free-text box ("make the crash cut deeper",
  "add a cash buffer parameter") → loops to rework with the spec updated;
  the build log appends the new attempt's cards. Show remaining
  iteration budget plainly ("2 revision rounds left on this run").
- **Discard** (quiet, confirm dialog; the run trace is still logged).
If the strategy is faithful-but-underperforming, this is where it is said
— as information, not judgment: "It does what you asked. On this smoke
test it trailed buy-and-hold. Adjust the blueprint, or save and run the
full evaluation."

### 3.8a Ask about this strategy (Q&A panel)
Below the decision card once a test flight exists — and it stays after
save (the build log is persisted, so is the conversation). One thread per
build; an evolve run is its own build with its own thread.
- Free-text question + three starter chips ("Why did the worst path end
  where it did?", "Which rule never fired…", "What would need to change…").
- Every question is triaged first. Off-topic gets a fixed, quiet refusal
  ("I can only answer questions about this strategy…") and costs nothing.
- Answers are Markdown, grounded in the code, the test-flight traces and
  the strategy's own `state_*` decision metrics (cited by name and year).
  **This is the one place the copy may be prescriptive** — "what would
  need to change?" gets a concrete parameter/rule change.
- When the answer proposes a change AND the run is paused at review, a
  **Use as refine feedback** button drops the change into the
  Request-changes textarea (scrolled into view, focused) — the user still
  presses Request changes. After save the button disappears; the thread
  stays readable.
- The same panel serves completed simulation reports ("Ask about these
  results") without the refine button.

### 3.9 Failure end-state (retry cap hit)
No dead ends. Card: "I couldn't get this working after 3 attempts."
- What was tried (attempt list, collapsed), which check kept failing.
- The last draft **saved automatically** (`validation_status='failed'`,
  as the old app did) — "kept as a draft you can inspect or retry".
- Suggestions: rephrase (with a specific hint derived from the failure
  mode), or start from a template.
- Credit note: honest statement of what was charged per the metering rule.

## 4. Streaming & state contract (API ↔ UI)

SSE event types (this is the contract; pin it in the API schema):
`run_started`, `stage_started{stage}`, `stage_progress{stage, message,
current?, total?}`, `stage_completed{stage, artifact}`,
`attempt_started{stage, attempt, max, reason}`, `needs_input{kind:
clarify|review, payload}`, `run_completed{strategy_id}`,
`run_failed{summary, draft_id}`.

**State is authoritative, SSE is enhancement:** `GET
/strategies/generate/{run_id}` returns the full run state (rebuilt from
the checkpoint) so a page reload — or returning tomorrow — rehydrates the
entire build log and re-subscribes. In-progress and needs-you runs appear
on `/strategies` as banners ("Your strategy 'Storm Shelter' has a
question for you"). Answering clarify/review goes through the resume
endpoint; the SSE stream then continues.

## 5. Components (shadcn inventory)

Stage rail (custom, small), Card + Accordion (build log), Badge (category
/ score / assumed), Table (parameters), existing `chart.tsx` (fan chart),
stat tiles (reuse the results-page pattern from W3), Textarea, RadioGroup
(clarify), AlertDialog (discard), Progress + Sonner (background nudges),
Tooltip wired to `/docs` glossary anchors. Code block: shiki or
`react-syntax-highlighter` (decide at build time; diff view needed for
evolve).

## 6. Copy rules (enforced in prompts AND in UI strings)

- Descriptive, never advisory. Banned framings: "you should", "best",
  "recommended strategy", "this will earn". Sole exception: Q&A answers
  (3.8a) when the user asks what would need to change — proposing a
  specific parameter value or rule change is the answer, not advice about
  the user's future.
- Every number that comes from 10 paths carries its uncertainty label.
- Jargon gets a glossary tooltip or a plainer word.
- The agent speaks in first person about *its process* ("I assumed…",
  "I couldn't get this working") — never about *the user's future*.

## 7. Open decisions (small, decide at build time)

1. Blueprint editing at review: free-text only (v1, decided-ish) vs.
   inline-editable rule list (nicer, more work — fast-follow).
2. Code visibility default: collapsed (spec'd above) — revisit if beta
   users turn out to be mostly programmers.
3. Concrete-path walkthrough (§3.7): requires per-year traces in the
   analyze artifact — confirm payload size is fine over SSE, else fetch
   lazily.
4. Mobile: rail → top progress dots + stacked cards (spec'd); verify the
   fan chart stays legible at 375px (known plotly squeeze from W3).
