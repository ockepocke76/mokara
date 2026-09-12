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


def spec_prompt(user_request: str, seed_name: str | None = None,
                seed_description: str | None = None, seed_code: str | None = None) -> str:
    seed_block = ""
    if seed_code:
        seed_block = (f"\nThe user is EVOLVING an existing strategy named "
                      f"'{seed_name}'. Its description: {seed_description}\n"
                      f"Its current code:\n```python\n{seed_code}\n```\n"
                      "Interpret the request as a change to this strategy; carry over its "
                      "mechanics except where the request changes them.\n")
    return f"""TASK: extract_spec
You turn a user's free-text request for a portfolio simulation strategy into a
structured spec. Be faithful to what they wrote; do not invent goals.

Set needs_clarification=true ONLY if the request is genuinely ambiguous on a
point that changes the strategy's structure (at most 3 questions, each with
concrete options). A merely underspecified detail gets a sensible default
recorded under assumptions instead.
{seed_block}
User request:
\"\"\"{user_request}\"\"\"

Respond with JSON matching:
{_spec_schema()}"""


def revise_spec_prompt(spec: dict, questions: list, answers: dict) -> str:
    return f"""TASK: revise_spec
Update this strategy spec with the user's clarification answers. Remove
resolved assumptions/questions, set needs_clarification=false, keep everything
else faithful to the original.

Current spec:
{json.dumps(spec, indent=2)}

Questions asked: {json.dumps(questions)}
User answers: {json.dumps(answers)}

Respond with JSON matching:
{_spec_schema()}"""


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
Respond with JSON:
{{
  "rules": ["rule 1", "rule 2", ...],
  "parameters": [{{"name": "...", "default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01, "description": "..."}}],
  "self_check": "one sentence confirming every spec mechanic maps to a rule, or naming what is missing"
}}"""


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


def static_review_prompt(code: str, plan: dict, spec: dict) -> str:
    return f"""TASK: static_review
Review this strategy code against its blueprint. For each rule, decide whether
the code actually implements it (not whether it compiles — a separate check
handles that). Also flag spec constraints the code violates and parameters
declared but never read.
{ENGINE_MECHANICS}
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
                   worst_path_trace: list[dict]) -> str:
    baseline_block = "No baseline comparison was run."
    if baseline_stats:
        baseline_block = (f"Baseline ('{baseline_name}', same market paths): "
                          f"{json.dumps(baseline_stats)}")
    return f"""TASK: analyze
A quick smoke test (10 simulated markets) ran for a newly generated strategy.
Judge ONE thing: does the observed behavior match the spec and blueprint?
Performance is NOT your verdict — a faithful strategy with poor numbers still
conforms; report the numbers neutrally and let the user decide. Never use
advisory language ("you should", "best") — describe only.

The smoke test always runs with the platform's default starting capital and a
fixed horizon; the strategy does not control that, and the user can set any
starting capital in real runs. If a spec phase (e.g. an accumulation phase
before a retirement trigger) simply cannot be observed under these test
conditions, that is NOT a mismatch: set conforms_to_spec=true and describe
the untested phase in notes so the user knows. Interest, fees, and taxes are
charged by the engine automatically — never call their absence from the
strategy's own arithmetic a mismatch.

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
