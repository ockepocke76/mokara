"""
Prompt builders for the strategy-generation graph.

Every prompt starts with a "TASK: <name>" marker (the fake provider keys on
it, and it makes traces greppable). The BaseStrategy contract is rendered
from the engine source via core.strategy_docs — never hand-maintained here.

Language rules baked into every user-facing text the LLM produces:
descriptive, never advisory ("the strategy withdrew X", not "you should").
"""
import json

from core.strategy_docs import strategy_api_docs

SANDBOX_RULES = """
## Sandbox rules (violations fail compilation or the dry run)
- The code runs in a RestrictedPython sandbox. Available globals: `BaseStrategy`,
  `np` (numpy), `pd` (pandas), `math`. NO import statements of any kind.
- Never access double-underscore attributes (`__dict__`, `__class__`, ...).
  Single-underscore helper methods (`self._helper`) are fine.
- Avoid in-place operators (`x += 1`); write `x = x + 1`.
- Persistent state goes in instance attributes set in `__init__` (call
  `super().__init__(params)` first). Read config with `self.params.get(key, default)`.
- `initialize_portfolio` must invest the starting cash:
  return `{'action': 'BUY_ASSET', 'cash_amount': initial_portfolio_state.get('cash', 0)}`
  (scale the amount only if the strategy deliberately holds a cash buffer).
- `execute_strategy_for_year` must return a dict with numeric values for ALL of:
  'amount_sold', 'amount_bought', 'debt_increase', 'debt_repayment', 'amount_contributed'.
- `evaluation_category()` must return 'WITHDRAWAL_ONLY', 'CONTRIBUTION_ONLY', or 'HYBRID'.
"""

ENGINE_MECHANICS = """
## Engine mechanics (the engine does these — never re-implement or demand them)
- Interest on outstanding debt is charged BY THE ENGINE every year, at the
  simulation's own loan interest rate. Management fees and taxes likewise.
  Their sum arrives as the `mandatory_costs` argument to
  execute_strategy_for_year: the strategy's job is only to FUND that amount
  (plus its desired drawdown), never to compute it.
- Therefore a strategy must NOT declare interest-rate/fee/tax parameters and
  must NOT subtract borrowing costs from its cash flows. Borrowing via
  'debt_increase' pays interest automatically — the bank is the engine.
- The user sets the simulation's starting capital and horizon at run time;
  the strategy must work with WHATEVER starting capital the engine hands it.
  Never treat starting capital as artificial or try to neutralize it.
"""

COMMON_MISTAKES = """
## Common mistakes seen in failed generations (avoid all of these)
- Using in-place operators (`+=`, `-=`) — the sandbox rewrites them poorly; write it out.
- Accessing dunder attributes or calling `open`/`eval`/`exec`/imports — hard blocked.
- Reading portfolio_history with Title Case keys ('Net Worth') — keys are
  lowercase snake_case ('net_worth').
- Returning a bare number from execute_strategy_for_year instead of the actions dict.
- Forgetting `evaluation_category()` or returning an invalid value from it.
- Defining parameters in `parameters` but never reading them via `self.params.get`
  (dead parameters).
- Dividing by portfolio values that can be zero — guard denominators.
"""

OUTPUT_FORMAT = """
## Output format (exactly this, nothing else)
<description>One or two sentences describing what the strategy does.</description>

```python
<the complete strategy class>
```
"""


def _spec_schema() -> str:
    return """{
  "summary": "one-sentence restatement of what the user wants",
  "category": "WITHDRAWAL_ONLY | CONTRIBUTION_ONLY | HYBRID",
  "mechanics": ["each distinct rule the user described, in their own vocabulary"],
  "assumptions": ["anything you had to assume because the request did not say"],
  "constraints": ["hard constraints the user stated (never borrow, keep cash buffer, ...)"],
  "proposed_parameters": [{"name": "snake_case_name", "default": 0.0, "description": "..."}],
  "suggested_name": "a short evocative strategy name",
  "needs_clarification": false,
  "questions": [{"question": "...", "options": ["...", "..."]}]
}"""


def spec_prompt(user_request: str) -> str:
    return f"""TASK: extract_spec
You turn a user's free-text request for a portfolio simulation strategy into a
structured spec. Be faithful to what they wrote; do not invent goals.

Set needs_clarification=true ONLY if the request is genuinely ambiguous on a
point that changes the strategy's structure (at most 3 questions, each with
concrete options). A merely underspecified detail gets a sensible default
recorded under assumptions instead.

User request:
\"\"\"{user_request}\"\"\"

Respond with JSON matching:
{_spec_schema()}"""


def _evolve_spec_schema() -> str:
    return """{
  "summary": "one-sentence restatement of the requested CHANGE",
  "category": "WITHDRAWAL_ONLY | CONTRIBUTION_ONLY | HYBRID — the current code's evaluation_category() unless a change alters it",
  "changes": ["each specific requested modification, atomic and precise (e.g. 'default of starting_assets: 100 -> 50')"],
  "change_scope": "parameter_only | behavioral | structural",
  "mechanics": ["the strategy's mechanics AFTER the change — read from the current code, altered only where a change applies"],
  "assumptions": ["anything you had to assume because the request did not say"],
  "constraints": ["hard constraints visible in the current code plus any new ones the request states"],
  "proposed_parameters": [{"name": "snake_case_name", "default": 0.0, "description": "the existing parameters with only the requested changes applied"}],
  "needs_clarification": false,
  "questions": [{"question": "...", "options": ["...", "..."]}]
}"""


def evolve_spec_prompt(user_request: str, seed_name: str | None,
                       seed_description: str | None, seed_code: str) -> str:
    return f"""TASK: evolve_spec
An existing, validated strategy is being EVOLVED: the user asked for a
specific change to it, NOT for a new strategy. Extract exactly WHAT changes;
everything else stays as it is in the current code.

The strategy: '{seed_name}'. Its description: {seed_description}
Its current code (the ground truth for mechanics and parameters):
```python
{seed_code}
```

change_scope definitions — pick the NARROWEST scope that honors the request:
- parameter_only: only values/defaults/ranges of EXISTING parameters change;
  no logic changes, no parameters added, removed, or renamed.
- behavioral: logic changes (rules, triggers, formulas), possibly adding or
  removing a parameter — but the strategy's core approach survives.
- structural: the request replaces the core approach; the strategy will be
  redesigned from scratch.

Do not invent improvements the user did not ask for. In proposed_parameters,
list the current code's parameters verbatim except where a change applies.

Set needs_clarification=true ONLY if the requested change is genuinely
ambiguous (at most 3 questions, each with concrete options).

User request:
\"\"\"{user_request}\"\"\"

Respond with JSON matching:
{_evolve_spec_schema()}"""


def revise_spec_prompt(spec: dict, questions: list, answers: dict) -> str:
    # An evolve spec (carries change_scope) must round-trip its own schema —
    # a dropped change_scope/changes would silently reroute the run.
    schema = _evolve_spec_schema() if 'change_scope' in spec else _spec_schema()
    return f"""TASK: revise_spec
Update this strategy spec with the user's clarification answers. Remove
resolved assumptions/questions, set needs_clarification=false, keep everything
else faithful to the original.

Current spec:
{json.dumps(spec, indent=2)}

Questions asked: {json.dumps(questions)}
User answers: {json.dumps(answers)}

Respond with JSON matching:
{schema}"""


def plan_prompt(spec: dict, examples_block: str) -> str:
    return f"""TASK: plan
Write the blueprint for a strategy implementing this spec: a numbered list of
plain-language rules a non-programmer can read ("Each year: ..."). Every
mechanic and constraint in the spec must map to a rule. Also design the
tunable parameters (snake_case, sensible defaults and ranges) — users interact
with the strategy mostly through these.

Spec:
{json.dumps(spec, indent=2)}
{ENGINE_MECHANICS}{examples_block}
Also choose test_initial_investment: the starting capital the 30-year smoke
test should run with so EVERY phase of the strategy can actually be observed.
An accumulation-from-income spec needs a small start (e.g. 10000 — a big
head start would trigger any retirement/target rule immediately); a
withdrawal spec needs a funded portfolio (e.g. 1000000).

Respond with JSON:
{{
  "rules": ["rule 1", "rule 2", ...],
  "parameters": [{{"name": "...", "default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01, "description": "..."}}],
  "test_initial_investment": 1000000,
  "self_check": "one sentence confirming every spec mechanic maps to a rule, or naming what is missing"
}}"""


def evolve_plan_prompt(spec: dict, seed_code: str) -> str:
    return f"""TASK: evolve_plan
Plan the edits for evolving an existing, validated strategy. The outcome of
this plan is a MINIMAL modification of the current code — not a new design.
Never rename, add, or remove a parameter, and never touch a mechanic, unless
a requested change explicitly calls for it.

Requested changes:
{json.dumps(spec.get('changes', []), indent=2)}

Current code (the ground truth being edited):
```python
{seed_code}
```
{ENGINE_MECHANICS}
The engine rules above are context for the edits — NEVER a reason to
restructure existing validated code beyond the requested changes.

Also choose test_initial_investment: the starting capital the 30-year smoke
test should run with so the CHANGED behavior can actually be observed (an
accumulation-from-income strategy needs a small start, a withdrawal strategy
a funded portfolio).

Respond with JSON:
{{
  "edits": [{{"target": "the exact method or property name the edit touches (one entry per touched method, including any NEW method or property an edit adds)", "change": "exactly what changes in it"}}],
  "rules": ["the strategy's full blueprint AFTER the edits: numbered plain-language rules restating the CURRENT code's behavior, altered only where an edit applies — the final code is reviewed against these"],
  "parameters": [{{"name": "...", "default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01, "description": "the current code's parameters verbatim except where an edit changes them"}}],
  "test_initial_investment": 1000000,
  "self_check": "one sentence confirming the edits cover every requested change and nothing else"
}}"""


def evolve_generate_prompt(spec: dict, plan: dict, seed_code: str, class_name: str,
                           feedback: str | None = None,
                           prior_code: str | None = None) -> str:
    feedback_block = ""
    if feedback:
        feedback_block = (f"\n## Fix this previous attempt\n"
                          f"The previous edit attempt produced:\n"
                          f"```python\n{prior_code}\n```\n"
                          f"What went wrong:\n{feedback}\n"
                          "Correct it with the SAME minimal-edit discipline: the result must\n"
                          "still be the original code plus only the planned edits. Produce the\n"
                          "complete corrected class (not a diff).\n")
    return f"""TASK: evolve_generate
You are EDITING an existing, working strategy class — not writing a new one.
Apply ONLY the planned edits to the current code below. Every line the edits
do not touch must be preserved verbatim: same class name ('{class_name}'),
same parameter names and defaults, same logic, same helper methods, same
comments. Do not restructure, rename, reformat, or "improve" anything the
edits do not require. Return the complete modified class.

Current code (the base you are editing):
```python
{seed_code}
```

Planned edits:
{json.dumps(plan.get('edits', []), indent=2)}

Requested changes (for context):
{json.dumps(spec.get('changes', []), indent=2)}

{strategy_api_docs()}
{ENGINE_MECHANICS}
The engine rules above are context for the edits — NEVER a reason to change
existing validated code beyond the planned edits.
{SANDBOX_RULES}
{COMMON_MISTAKES}
{feedback_block}
{OUTPUT_FORMAT}"""


def generate_prompt(spec: dict, plan: dict, examples_block: str, class_name: str,
                    feedback: str | None = None, prior_code: str | None = None) -> str:
    feedback_block = ""
    if feedback:
        feedback_block = (f"\n## Fix this previous attempt\n"
                          f"```python\n{prior_code}\n```\n"
                          f"What went wrong:\n{feedback}\n"
                          "Produce a corrected complete class (not a diff).\n")
    return f"""TASK: generate
You write Python strategy classes for a Monte Carlo portfolio simulator. Write
a class named '{class_name}' that inherits from 'BaseStrategy' and implements
this blueprint exactly. Implement every rule; expose exactly the planned
parameters via the `parameters` property AND read each one with
`self.params.get(...)` (no dead parameters).

Blueprint:
{json.dumps(plan, indent=2)}

Spec (for context):
{json.dumps(spec, indent=2)}

{strategy_api_docs()}
{ENGINE_MECHANICS}
{SANDBOX_RULES}
{COMMON_MISTAKES}
{examples_block}
{feedback_block}
{OUTPUT_FORMAT}"""


def static_review_prompt(code: str, plan: dict, spec: dict,
                         seed_code: str | None = None) -> str:
    evolution_block = ""
    if seed_code:
        evolution_block = (f"\nThis code is an EVOLUTION of an existing strategy. "
                           f"Requested changes:\n{json.dumps(spec.get('changes', []), indent=2)}\n"
                           f"Original code before the change:\n```python\n{seed_code}\n```\n"
                           "Additionally flag as issues any UNREQUESTED differences: original "
                           "mechanics, parameters, or defaults that were dropped or altered "
                           "with no requested change calling for it.\n")
    return f"""TASK: static_review
Review this strategy code against its blueprint. For each rule, decide whether
the code actually implements it (not whether it compiles — a separate check
handles that). Also flag spec constraints the code violates and parameters
declared but never read.
{evolution_block}{ENGINE_MECHANICS}
Judge blueprint rules THROUGH the engine's division of labor: a rule about
paying interest, fees, or taxes is implemented by borrowing/holding assets at
all — the engine charges those costs. Never fail a rule because the code does
not compute interest or deduct borrowing costs itself.

Blueprint rules:
{json.dumps(plan.get('rules', []), indent=2)}

Spec constraints: {json.dumps(spec.get('constraints', []))}

Code:
```python
{code}
```

Respond with JSON:
{{
  "implements_blueprint": true,
  "rule_verdicts": [{{"rule": "...", "implemented": true, "note": "..."}}],
  "issues": ["each concrete problem, empty if none"]
}}"""


def analyze_prompt(spec: dict, plan: dict, summary_stats: dict,
                   baseline_stats: dict | None, baseline_name: str | None,
                   worst_path_trace: list[dict],
                   test_capital: float | None = None,
                   evolution: dict | None = None) -> str:
    baseline_block = "No baseline comparison was run."
    if baseline_stats:
        baseline_block = (f"Baseline ('{baseline_name}', same market paths): "
                          f"{json.dumps(baseline_stats)}")
    evolution_block = ""
    if evolution:
        if evolution.get('baseline_ran'):
            comparison = (
                "The baseline in this prompt IS the pre-change version of this "
                "strategy, run on identical market paths. Judge conformance as: "
                "(1) the requested change is reflected in the observed behavior "
                "where these test conditions can show it; (2) behavior the change "
                "does not touch tracks the pre-change baseline — a large divergence "
                "the requested change cannot explain is a mismatch.")
        else:
            comparison = (
                "No pre-change baseline comparison was available for this test. "
                "Judge only whether the requested change is reflected in the "
                "observed behavior where these test conditions can show it; do "
                "not invent a before/after comparison.")
        evolution_block = (
            f"\nThis run EVOLVED the existing strategy '{evolution.get('seed_name')}'. "
            f"Requested changes:\n{json.dumps(evolution.get('changes', []), indent=2)}\n"
            f"{comparison} The explanation you write describes the strategy as it "
            "now is, not the change.\n")
    capital_block = ""
    if test_capital is not None:
        capital_block = (f"\nTest conditions: every path starts with "
                         f"${test_capital:,.0f} already invested. Judge trigger "
                         f"timing against THAT capital plus market growth — a "
                         f"threshold rule that fires because the starting "
                         f"portfolio already satisfies it is behaving "
                         f"correctly, not prematurely.\n")
    return f"""TASK: analyze
A quick smoke test (10 simulated markets) ran for a newly generated strategy.
{capital_block}{evolution_block}
Judge ONE thing: does the observed behavior match the spec and blueprint?
Performance is NOT your verdict — a faithful strategy with poor numbers still
conforms; report the numbers neutrally and let the user decide. Never use
advisory language ("you should", "best") — describe only.

The smoke test runs with the platform's standardized starting capital for the
strategy's category and a fixed horizon; the strategy does not control that,
and the user can set any starting capital in real runs. If a spec behavior
(a rare trigger, a phase the horizon never reaches) simply cannot be observed
under these test conditions, that is NOT a mismatch: set
conforms_to_spec=true and describe the untested behavior in notes so the user
knows. Interest, fees, and taxes are charged by the engine automatically —
never call their absence from the strategy's own arithmetic a mismatch.

Spec:
{json.dumps(spec, indent=2)}

Blueprint rules:
{json.dumps(plan.get('rules', []), indent=2)}

Strategy summary stats: {json.dumps(summary_stats)}
{baseline_block}

Worst test path, year by year (net worth, withdrawal, sales, borrowing):
{json.dumps(worst_path_trace)}

Respond with JSON:
{{
  "conforms_to_spec": true,
  "mismatches": ["each observed behavior that contradicts the spec/blueprint, empty if none"],
  "typical_year": "1-2 sentences: what the strategy does in a normal year, with real numbers",
  "worst_path_story": "2-3 sentences: what it did in the worst test path, with real numbers",
  "explanation": "3-4 sentence plain-language description of the strategy's behavior (saved as its description)",
  "notes": "anything worth telling the user, e.g. a rule the 10 paths never triggered"
}}"""


def format_examples_block(examples: list[dict]) -> str:
    if not examples:
        return ""
    parts = ["\n## Reference examples (validated strategies; match their style and structure)"]
    for ex in examples:
        parts.append(f"### {ex['name']}\nUser asked for: {ex['prompt']}\n"
                     f"```python\n{ex['code']}\n```")
    return "\n".join(parts)
