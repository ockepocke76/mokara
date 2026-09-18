"""
Tiered LLM access for the strategy-generation graph.

Nodes never talk to a provider directly: they receive a callable
(prompt, tier, json_mode) -> text via the graph config, so tests inject a
stub and MOKARA_FAKE_LLM=1 runs the whole designer flow without an API key.
The real implementation stays on core.llm.call_gemini_safe (no langchain
model layer, per the W5 design).

Model tiers: 'fast' for spec/clarify/review-style calls, 'strong' for
code generation and analysis. Override with GEMINI_MODEL_FAST/_STRONG.
"""
import json
import logging
import os
import re


class LLMError(RuntimeError):
    """Provider-level failure (quota, network, empty response)."""


def _model_for(tier: str) -> str:
    if tier == 'strong':
        return os.environ.get('GEMINI_MODEL_STRONG', 'gemini-3.8-flash')
    return os.environ.get('GEMINI_MODEL_FAST', 'gemini-3.5-flash-lite')


def real_llm_call(prompt: str, tier: str = 'fast', json_mode: bool = False) -> str:
    from core.llm import call_gemini_safe

    config = {'response_mime_type': 'application/json'} if json_mode else None
    text, error, _usage = call_gemini_safe(_model_for(tier), prompt, generation_config=config)
    if error or not text:
        raise LLMError(error or "Empty response from LLM")
    return text


def get_llm_call():
    if os.environ.get('MOKARA_FAKE_LLM') == '1':
        logging.warning("MOKARA_FAKE_LLM=1 — strategy generation is using canned LLM responses")
        return fake_llm_call
    return real_llm_call


def parse_json_response(text: str) -> dict:
    """Parse a JSON object from an LLM response, tolerating code fences."""
    cleaned = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", cleaned, re.DOTALL)
    if fence:
        cleaned = fence.group(1).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM response was not valid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON response was not an object")
    return parsed


def extract_description_and_code(text: str) -> tuple[str, str]:
    """
    Extract <description> and the python code block from a codegen response.
    Ported from the old app's extraction cascade (ui/strategy_common.py).
    """
    description = ""
    match = re.search(r"<description>(.*?)</description>", text, re.DOTALL)
    if match:
        description = match.group(1).strip()

    code = ""
    if "```python" in text:
        code = text.split("```python", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        code = text.split("```", 1)[1].split("```", 1)[0].strip()
    elif "class " in text and "(BaseStrategy):" in text:
        code = text.strip()

    if not code:
        raise ValueError("Could not extract strategy code from the LLM response.")
    return description, code


# --- Canned provider (dev/e2e without an API key; also handy in tests) -----

_FAKE_CODE_TEMPLATE = '''
class {class_name}(BaseStrategy):
    @property
    def parameters(self):
        return {{'withdrawal_rate': {{'description': 'Annual withdrawal rate',
                                      'default': 0.04, 'min': 0.01, 'max': 0.10, 'step': 0.005}}}}

    @property
    def shortfall_funding_policy(self):
        return ['USE_CASH', 'SELL_ASSETS']

    def initialize_portfolio(self, initial_portfolio_state, market_data_at_start):
        return {{'action': 'BUY_ASSET', 'cash_amount': initial_portfolio_state.get('cash', 0)}}

    def get_annual_drawdown(self, year, portfolio_state, portfolio_history):
        rate = self.params.get('withdrawal_rate', 0.04)
        base = self.params.get('initial_investment', 1000000) * rate
        inflation = self.params.get('inflation_rate', 0.02)
        return base * ((1 + inflation) ** (year - 1))

    def execute_strategy_for_year(self, year, portfolio_state, portfolio_history, desired_drawdown, mandatory_costs):
        need = desired_drawdown + mandatory_costs
        return {{'amount_sold': need, 'amount_bought': 0.0,
                 'debt_increase': 0.0, 'debt_repayment': 0.0, 'amount_contributed': 0.0}}

    def evaluation_category(self):
        return 'WITHDRAWAL_ONLY'
'''


def fake_llm_call(prompt: str, tier: str = 'fast', json_mode: bool = False) -> str:
    """Deterministic canned responses, keyed by the TASK marker each prompt carries."""
    task_match = re.search(r"^TASK: (\w+)", prompt)
    task = task_match.group(1) if task_match else ""

    if task == 'extract_spec':
        wants_clarify = '???' in prompt
        return json.dumps({
            "summary": "An inflation-adjusted fixed-rate withdrawal strategy.",
            "category": "WITHDRAWAL_ONLY",
            "mechanics": ["Invest everything at the start.",
                          "Withdraw a fixed percentage of the initial portfolio each year.",
                          "Adjust the withdrawal for inflation every year."],
            "assumptions": ["Assumed a 4% withdrawal rate — the request did not name one."],
            "constraints": [],
            "proposed_parameters": [{"name": "withdrawal_rate", "default": 0.04,
                                     "description": "Annual withdrawal rate"}],
            "suggested_name": "Steady Withdrawal",
            "needs_clarification": wants_clarify,
            "questions": ([{"question": "What annual withdrawal rate do you want?",
                            "options": ["3%", "4%", "5%"]}] if wants_clarify else []),
        })
    if task == 'revise_spec':
        if '"change_scope"' in prompt:
            return fake_llm_call("TASK: evolve_spec\n(no ???)", tier, json_mode)
        return fake_llm_call("TASK: extract_spec\n(no ???)", tier, json_mode)
    if task == 'evolve_spec':
        wants_clarify = '???' in prompt
        # 'completely' in the request marks a structural rebuild in tests.
        structural = 'completely' in prompt
        return json.dumps({
            "summary": "Change the withdrawal rate default from 4% to 5%.",
            "category": "WITHDRAWAL_ONLY",
            "changes": ["default of withdrawal_rate: 0.04 -> 0.05"],
            "change_scope": "structural" if structural else "parameter_only",
            "mechanics": ["Invest everything at the start.",
                          "Withdraw a fixed percentage of the initial portfolio each year.",
                          "Adjust the withdrawal for inflation every year."],
            "assumptions": [],
            "constraints": [],
            "proposed_parameters": [{"name": "withdrawal_rate", "default": 0.05,
                                     "description": "Annual withdrawal rate"}],
            "needs_clarification": wants_clarify,
            "questions": ([{"question": "Which default do you want?",
                            "options": ["0.05", "0.045"]}] if wants_clarify else []),
        })
    if task == 'evolve_plan':
        return json.dumps({
            "edits": [{"target": "parameters",
                       "change": "change the withdrawal_rate default from 0.04 to 0.05"}],
            "rules": ["Invest 100% of the starting cash into the asset in year 0.",
                      "Each year, withdraw the initial portfolio value times the withdrawal rate, adjusted for inflation.",
                      "Fund withdrawals by selling assets; never borrow."],
            "parameters": [{"name": "withdrawal_rate", "default": 0.05, "min": 0.01,
                            "max": 0.10, "description": "Annual withdrawal rate"}],
            "test_initial_investment": 1000000,
            "self_check": "The single edit covers the single requested change."})
    if task == 'evolve_generate':
        # A faithful minimal edit: the seed code (the prompt's first python
        # fence) with only the default changed.
        seed = prompt.split("```python", 1)[1].split("```", 1)[0]
        edited = seed.replace("'default': 0.04", "'default': 0.05").strip()
        return ("<description>Withdraws a fixed, inflation-adjusted 5% of the "
                "initial portfolio every year, funded by selling assets.</description>\n"
                f"```python\n{edited}\n```")
    if task == 'plan':
        return json.dumps({
            "rules": ["Invest 100% of the starting cash into the asset in year 0.",
                      "Each year, withdraw the initial portfolio value times the withdrawal rate, adjusted for inflation.",
                      "Fund withdrawals by selling assets; never borrow."],
            "parameters": [{"name": "withdrawal_rate", "default": 0.04, "min": 0.01,
                            "max": 0.10, "description": "Annual withdrawal rate"}],
            "self_check": "The rules cover initialization, annual withdrawal sizing, and funding."})
    if task == 'generate':
        name_match = re.search(r"named '(\w+)'", prompt)
        class_name = name_match.group(1) if name_match else "CustomStrategy"
        return ("<description>Withdraws a fixed, inflation-adjusted percentage of the "
                "initial portfolio every year, funded by selling assets.</description>\n"
                f"```python\n{_FAKE_CODE_TEMPLATE.format(class_name=class_name)}\n```")
    if task == 'static_review':
        return json.dumps({"implements_blueprint": True, "issues": [],
                           "rule_verdicts": [{"rule": "Invest at start", "implemented": True, "note": ""},
                                             {"rule": "Inflation-adjusted withdrawal", "implemented": True, "note": ""},
                                             {"rule": "Sell to fund", "implemented": True, "note": ""}]})
    if task == 'analyze':
        return json.dumps({
            "conforms_to_spec": True, "mismatches": [],
            "typical_year": "In a typical year the strategy sells just enough assets to cover the "
                            "inflation-adjusted withdrawal and lets the rest ride.",
            "worst_path_story": "In the worst test path the portfolio fell sharply early on; the strategy "
                                "kept withdrawing the planned amount, which accelerated depletion.",
            "explanation": "A fixed-rate, inflation-adjusted withdrawal strategy funded by asset sales. "
                           "It never borrows and holds no cash buffer.",
            "notes": "Behavior matched the blueprint in all test paths."})
    raise LLMError(f"fake_llm_call has no canned response for task '{task}'")
