from RestrictedPython import compile_restricted, RestrictingNodeTransformer
from RestrictedPython.Guards import safe_builtins
from RestrictedPython.Guards import full_write_guard
from RestrictedPython.Eval import default_guarded_getiter
from RestrictedPython.Eval import default_guarded_getitem
#from RestrictedPython.Guards import guarded_getiter
#from RestrictedPython.Guards import guarded_getitem
from RestrictedPython.Guards import guarded_iter_unpack_sequence
from .strategy import BaseStrategy
import logging
import numpy as np
import pandas as pd
import re

# --- Define the Sandboxed Environment ---

# Start with a set of safe, common built-in functions.
# This excludes dangerous ones like `open`, `eval`, `exec`, etc.
_safe_globals = safe_builtins.copy()

# Add any custom functions or classes the sandboxed code needs access to.
# Crucially, it needs access to the BaseStrategy class to inherit from it.
_safe_globals['BaseStrategy'] = BaseStrategy

# RestrictedPython's class compilation can sometimes require __metaclass__.
# We provide the default 'type' to satisfy this requirement.
_safe_globals['__metaclass__'] = type

# Optionally, add other safe utilities if needed.
# For example, allowing the 'math' library is generally safe.
import math
_safe_globals['math'] = math
_safe_globals['np'] = np
_safe_globals['pd'] = pd

def _sandboxed_getattr(obj, name):
    """
    Custom `_getattr_` guard for RestrictedPython.

    By default, RestrictedPython's `safer_getattr` blocks access to any
    attribute starting with an underscore. This custom guard relaxes that rule
    to allow access to single-underscore attributes (e.g., `_my_helper`),
    which is useful for LLM-generated code that uses them for internal helpers.
    It continues to block access to double-underscore attributes (e.g., `__mangled`)
    to maintain a strong security boundary.
    """
    if name == '__init__':
        pass
    elif name.startswith('__'):
        raise AttributeError(f'Access to double-underscore attributes like "{name}" is not allowed in the sandbox.')
    return getattr(obj, name)

_safe_globals['_getattr_'] = _sandboxed_getattr


def _normalize_key(key):
    """Helper to convert a key to a standardized format (lowercase, snake_case)."""
    if isinstance(key, str):
        return key.lower().replace(' ', '_')
    return key

# Add required RestrictedPython utility functions for safe operations.

# --- FIX: Use the official, guarded utility functions from the library ---
# This ensures compatibility with all forms of standard Python syntax (loops,
# item access, unpacking) and is more robust than handwritten patches.
_safe_globals['_getiter_'] = default_guarded_getiter
_safe_globals['_getitem_'] = default_guarded_getitem

# Custom unpack sequence function that handles tuples from function returns
# The default guarded_iter_unpack_sequence has issues with tuple returns
def _simple_unpack_sequence(it, spec, _getiter_):
    """Simple unpack sequence that handles tuples/lists directly."""
    # For tuples and lists, just convert to list and return
    if isinstance(it, (tuple, list)):
        return list(it)
    # For other iterables, use the iterator
    return list(_getiter_(it))

_safe_globals['_iter_unpack_sequence_'] = _simple_unpack_sequence
_safe_globals['_unpack_sequence_'] = _simple_unpack_sequence

def _strategy_write_guard(obj):
    """
    Custom write guard for our strategy sandbox.
    
    The default RestrictedPython '_write_' (full_write_guard) is often too restrictive
    for standard Python classes. We use this custom name to ensure our guard is 
    always preferred and never overridden by RestrictedPython internals.
    """
    if obj is None or isinstance(obj, (bool, int, float, complex, str, bytes, type)):
        raise TypeError("attribute-less object (assign or del)")
    return obj

_safe_globals['_strategy_write_'] = _strategy_write_guard
_safe_globals['_write_'] = _strategy_write_guard # Fallback for any internal uses

import ast
from RestrictedPython.transformer import copy_locations, INSPECT_ATTRIBUTES

class StrategyPolicy(RestrictingNodeTransformer):
    """
    A custom security policy for RestrictedPython.
    By default, RestrictedPython forbids any name starting with an underscore.
    This policy overrides that behavior to allow specific "private" helper methods
    that an LLM might generate for code organization within a strategy class.
    """
    # List of underscore-prefixed names that are considered safe to use.

    def check_name(self, node, name, allow_magic_methods=False):
        """
        Override the default name check to allow single-underscore names.
        This allows the LLM to generate "private" helper methods (e.g., `_my_helper`).
        It continues to block double-underscore names to prevent access to mangled attributes.
        """
        if name is None:
            return node
        
        if name.startswith('__') and not allow_magic_methods:
            logging.error(f"DEBUG SANDBOX: Blocking name '{name}' at line {getattr(node, 'lineno', '?')}")
            self.error(node, f'"{name}" is an invalid variable name because it starts with "__".')
        return node

    def visit_Attribute(self, node):
        """
        Override the default attribute visitor to allow single-underscore attributes.
        The default RestrictedPython behavior blocks ALL underscore-prefixed attributes,
        but we want to allow single-underscore ones (e.g., `self._my_helper`) while
        still blocking double-underscore ones (e.g., `self.__dict__`) for security.
        """
        if node.attr == '__init__':
            # Allow access to __init__ specifically to support super().__init__() calls
            # This is safe because we still control the class definition and can block other magic methods if needed.
            pass
        elif node.attr.startswith('__'):
            self.error(
                node,
                f'"{node.attr}" is an invalid attribute name because it starts with "__".')

        if node.attr.endswith('__roles__'):
            self.error(
                node,
                f'"{node.attr}" is an invalid attribute name because it ends with "__roles__".')

        if node.attr in INSPECT_ATTRIBUTES:
            self.error(
                node,
                f'"{node.attr}" is a restricted name that is forbidden to access in RestrictedPython.',
            )

        if isinstance(node.ctx, ast.Load):
            node = self.node_contents_visit(node)
            new_node = ast.Call(
                func=ast.Name('_getattr_', ast.Load()),
                args=[node.value, ast.Constant(node.attr)],
                keywords=[])

            copy_locations(new_node, node)
            return new_node

        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            node = self.node_contents_visit(node)
            new_value = ast.Call(
                func=ast.Name('_strategy_write_', ast.Load()),
                args=[node.value],
                keywords=[])

            copy_locations(new_value, node.value)
            node.value = new_value
            return node

        else:  # pragma: no cover
            raise NotImplementedError(f"Unknown ctx type: {type(node.ctx)}")

class SandboxedStrategyWrapper(BaseStrategy):
    """
    A wrapper class that sits between the simulation engine and the LLM-generated
    strategy. Its purpose is to transform the input data (like portfolio_history)
    into a standardized format (all dict keys are lowercase snake_case) before
    passing it to the sandboxed code. This simplifies the LLM's task and makes
    the simulation engine cleaner.
    """
    def __init__(self, sandboxed_strategy_instance: BaseStrategy):
        # The wrapper holds an instance of the actual LLM-generated strategy.
        self.sandboxed_strategy = sandboxed_strategy_instance
        # It also needs access to the parameters, so we copy them over.
        super().__init__(self.sandboxed_strategy.params)

    @property
    def parameters(self):
        """
        Delegates the parameters property to the wrapped strategy instance.
        """
        return self.sandboxed_strategy.parameters

    @property
    def shortfall_funding_policy(self) -> list[str]:
        """
        Delegates the shortfall funding policy to the wrapped strategy instance.
        """
        return self.sandboxed_strategy.shortfall_funding_policy

    def initialize_portfolio(self, initial_portfolio_state: dict, market_data_at_start: pd.DataFrame) -> dict:
        # No transformation needed here, just pass through.
        return self.sandboxed_strategy.initialize_portfolio(initial_portfolio_state, market_data_at_start)

    def get_annual_drawdown(self, year: int, portfolio_state: dict, portfolio_history: list[dict]) -> float:
        # Normalize all keys in the history to lowercase snake_case.
        robust_history = [{_normalize_key(k): v for k, v in item.items()} for item in portfolio_history]
        return self.sandboxed_strategy.get_annual_drawdown(year, portfolio_state, robust_history)

    def execute_strategy_for_year(self, year: int, portfolio_state: dict, portfolio_history: list[dict], desired_drawdown: float, mandatory_costs: float) -> dict:
        # Normalize all keys in the history to lowercase snake_case.
        robust_history = [{_normalize_key(k): v for k, v in item.items()} for item in portfolio_history]
        return self.sandboxed_strategy.execute_strategy_for_year(year, portfolio_state, robust_history, desired_drawdown, mandatory_costs)

def _slugify_to_classname(text: str) -> str:
    """Converts a string into a valid Python class name."""
    # Remove invalid characters, then capitalize each word and join them.
    text = re.sub(r'[^a-zA-Z0-9_ ]', '', text)
    return "".join(word.capitalize() for word in text.split())

def _validate_strategy_class(strategy_class):
    """
    Validates a strategy class by attempting to instantiate it.
    Raises an exception if the class cannot be instantiated.
    """
    logging.info(f"Performing dry run validation for {strategy_class.__name__}")
    try:
        # 1. Create mock data that mirrors the real simulation environment.
        mock_params = {'initial_investment': 1000000, 'inflation_rate': 0.02}
        mock_portfolio_state = {
            'asset_value': 1000000,
            'debt': 0,
            'cash': 0,
            'cost_basis': 1000000,
            'net_worth': 1000000  # asset_value - debt + cash
        }
        
        # Use a slightly more realistic history with a few years of data.
        # This increases the chance that loops inside the strategy code will execute
        # during the dry run, catching errors like missing '_getiter_'.
        # Include all fields that strategies might access from portfolio_history.
        raw_history = [
            {'Year': 0, 'Asset Value': 1000000, 'Debt': 0, 'Cash': 0, 'Net Worth': 1000000,
             'Consumption Delivered': 0, 'Amount Sold': 0, 'Amount Bought': 0, 'Amount Contributed': 0,
             'Debt Change': 0, 'Interest Paid': 0, 'Tax Paid': 0, 'Fees Paid': 0,
             'Accumulated Interest': 0, 'Accumulated Tax': 0, 'Accumulated Fees': 0, 'Cash Interest': 0},
            {'Year': 1, 'Asset Value': 1100000, 'Debt': 40000, 'Cash': 0, 'Net Worth': 1060000,
             'Consumption Delivered': 40000, 'Amount Sold': 40000, 'Amount Bought': 0, 'Amount Contributed': 0,
             'Debt Change': 40000, 'Interest Paid': 800, 'Tax Paid': 2000, 'Fees Paid': 500,
             'Accumulated Interest': 800, 'Accumulated Tax': 2000, 'Accumulated Fees': 500, 'Cash Interest': 0}
        ]
        # Normalize the mock history keys to match what the SandboxedStrategyWrapper will do in a real run.
        # This ensures the validation dry run accurately tests the AI's adherence to the key format rule.
        mock_portfolio_history = [{_normalize_key(k): v for k, v in item.items()} for item in raw_history]

        # 2. Instantiate the strategy WITH params dict (required by BaseStrategy)
        instance = strategy_class(mock_params)
        
        
        if hasattr(instance, 'parameters') and isinstance(instance.parameters, dict):
            for key, value in instance.parameters.items():
                if isinstance(value, dict) and 'default' in value:
                    mock_params[key] = value.get('default')
            # Update params with defaults
            instance.params = mock_params

        # 3. Call initialize_portfolio and validate its output.
        initial_actions = instance.initialize_portfolio(mock_portfolio_state, pd.DataFrame())
        if not isinstance(initial_actions, dict):
            raise TypeError(f"initialize_portfolio must return a dictionary, but returned {type(initial_actions)}")

        cash_amount = initial_actions.get('cash_amount', 0.0)
        if not isinstance(cash_amount, (int, float)):
            raise TypeError("The 'cash_amount' value in the dictionary returned by initialize_portfolio must be a number.")

        # 4. Call the other core methods to check for immediate errors.
        desired_drawdown = instance.get_annual_drawdown(1, mock_portfolio_state, mock_portfolio_history)
        
        # Ensure desired_drawdown is a number to prevent downstream errors
        if not isinstance(desired_drawdown, (int, float, np.number)):
            raise TypeError(f"get_annual_drawdown must return a number (int or float), but returned {type(desired_drawdown)}")

        # 5. Validate the return value of execute_strategy_for_year.
        strategy_results = instance.execute_strategy_for_year(1, mock_portfolio_state, mock_portfolio_history, desired_drawdown, mandatory_costs=1000.0)
        if not isinstance(strategy_results, dict):
            raise TypeError(f"execute_strategy_for_year must return a dictionary, but returned {type(strategy_results)}")

        amount_sold = strategy_results.get('amount_sold', 0.0)
        debt_increase = strategy_results.get('debt_increase', 0.0)
        if not isinstance(amount_sold, (int, float)) or not isinstance(debt_increase, (int, float)):
            raise TypeError("The 'amount_sold' and 'debt_increase' values in the returned dictionary must be numbers.")

        # 6. Validate the shortfall_funding_policy property.
        policy = instance.shortfall_funding_policy
        if not isinstance(policy, list):
            raise TypeError(f"shortfall_funding_policy must return a list, but returned {type(policy)}")
        
        valid_options = {'USE_CASH', 'SELL_ASSETS', 'BORROW'}
        if not policy:
            raise ValueError("shortfall_funding_policy cannot be an empty list.")
        for item in policy:
            if item not in valid_options:
                raise ValueError(f"Invalid option '{item}' in shortfall_funding_policy. Valid options are: {valid_options}")

        # 7. Validate evaluation_category. The base class defaults to 'HYBRID',
        # so this only fails when a strategy overrides it with a bad value.
        category = instance.evaluation_category()
        valid_categories = {'WITHDRAWAL_ONLY', 'CONTRIBUTION_ONLY', 'HYBRID'}
        if category not in valid_categories:
            raise ValueError(f"evaluation_category() returned '{category}'. Valid options are: {valid_categories}")

        logging.info(f"Dry run validation successful for {strategy_class.__name__}")
        return True
    except Exception as e:
        logging.error(f"Strategy validation dry run failed: {e}", exc_info=True)
        raise # Re-raise the exception to be caught by the caller

def _rewrite_inplace_assignments(code: str) -> str:
    """
    Rewrites in-place assignments (e.g., x += 1) to their explicit
    equivalents (e.g., x = x + 1) to avoid a bug in RestrictedPython's
    AST transformer that causes a NameError for '_inplacevar_'.
    """
    # List of in-place operators and their standard equivalents
    operators = {
        '+': '+=',
        '-': '-=',
        '*': '*=',
        '/': '/=',
        '%': '%=',
        '**': '**=',
        '//': '//='
    }

    # Split the code into lines to process them individually
    lines = code.split('\n')
    rewritten_lines = []

    for line in lines:
        # Preserve indentation
        indentation = re.match(r'^\s*', line).group(0)
        stripped_line = line.strip()

        # Check if the line contains an in-place assignment
        found = False
        for op_symbol, op_assign in operators.items():
            if op_assign in stripped_line:
                # A simple but effective regex to capture the target and the value
                # It captures everything before the operator as the target, and everything after as the value.
                pattern = re.compile(r'(.+?)\s*' + re.escape(op_assign) + r'\s*(.+)')
                match = pattern.match(stripped_line)
                if match:
                    target, value = match.groups()
                    # Reconstruct the line as an explicit assignment
                    rewritten_line = f"{indentation}{target.strip()} = {target.strip()} {op_symbol} {value.strip()}"
                    rewritten_lines.append(rewritten_line)
                    found = True
                    break # Move to the next line once a match is found and replaced
        
        if not found:
            rewritten_lines.append(line)

    return '\n'.join(rewritten_lines)


def execute_strategy_code(code_string: str, strategy_class_name: str = "CustomStrategy"):
    """
    Safely compiles and executes a string of Python code to define a custom strategy class.

    This function uses RestrictedPython to create a sandboxed environment, preventing
    the execution of unsafe code (e.g., file I/O, network access).

    Args:
        code_string (str): The Python code for the strategy class, as generated by an LLM.
        strategy_class_name (str): The expected name of the strategy class in the code.

    Returns:
        The dynamically created strategy class if successful and safe, otherwise None.
    """
    try:
        logging.info(f"Attempting to execute sandboxed code for strategy: {strategy_class_name}")
        
        if "import os" in code_string:
            raise ValueError("disallowed import")

        # --- FIX: Pre-process the code to remove in-place assignments ---
        # This is a workaround for a bug in RestrictedPython's AST transformer
        # that causes a NameError for '_inplacevar_'.
        code_string = _rewrite_inplace_assignments(code_string)

        # 1. Compile the code in a restricted environment.
        # The '<string>' argument is a dummy filename for error messages.
        try:
            byte_code = compile_restricted(code_string, '<string>', 'exec', policy=StrategyPolicy)
        except Exception as e:
            logging.error(f"Compilation/Syntax Error in Sandbox Code: {e}")
            # Add line numbers to code for easier debugging
            numbered_code = "\n".join([f"{i+1:3d}: {line}" for i, line in enumerate(code_string.splitlines())])
            logging.error(f"--- FAILED CODE ---\n{numbered_code}\n-------------------")
            raise

        # 2. Prepare a local namespace for the execution.
        local_namespace = {}

        # 3. Execute the compiled code. The result will populate local_namespace.
        exec(byte_code, _safe_globals, local_namespace)

        # 4. Extract the newly defined class from the namespace.
        strategy_class = local_namespace.get(strategy_class_name)

        # --- MECHANISM: Robust Class Discovery ---
        # If the expected class name isn't found, scan the namespace for *any* valid strategy class.
        # This acts as a safety net if the LLM ignores the naming rule.
        if not strategy_class:
            candidates = []
            for name, obj in local_namespace.items():
                try:
                    # Check if it's a class, inherits from BaseStrategy, and IS NOT BaseStrategy itself
                    if isinstance(obj, type) and issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                        candidates.append(obj)
                except Exception:
                    pass
            
            if candidates:
                # If we found one, use it. If multiple, use the last one (heuristic).
                strategy_class = candidates[-1]
                logging.warning(
                    f"⚠️ Class Name Mismatch: Expected '{strategy_class_name}', but found '{strategy_class.__name__}'. "
                    f"Auto-correcting to use discovered class."
                )
            else:
                # If strictly no candidates found, then we fail.
                logging.error(f"No valid strategy class found in namespace. Keys: {list(local_namespace.keys())}")
        # -----------------------------------------

        if not strategy_class or not issubclass(strategy_class, BaseStrategy):
            error_msg = f"Class '{strategy_class_name}' not found or does not inherit from 'BaseStrategy'. Please ensure the class is correctly named and inherits from the base class (e.g., `class {strategy_class_name}(BaseStrategy):`)."
            logging.error(f"Sandbox validation failed: {error_msg}")
            raise ValueError(error_msg)

        # 5. Perform a dry run validation to catch runtime errors like KeyErrors.
        # This is re-raised as an exception to be handled by the UI.
        _validate_strategy_class(strategy_class)

        logging.info(f"Successfully executed and validated sandboxed strategy class: {strategy_class_name}")
        # Return the user's strategy class. The calling code is responsible for wrapping it.
        return strategy_class
    except Exception as e:
        logging.error(f"An error occurred during sandboxed execution: {e}", exc_info=True)
        # Re-raise the exception so it can be caught and displayed by the UI.
        raise