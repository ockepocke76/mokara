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
import multiprocessing
import os
import types
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

# --- Module/attribute access policy ---------------------------------------
# numpy and pandas are useful to strategies but full of escape hatches:
# pickle loaders (read_pickle / np.load = arbitrary code execution), file
# readers/writers (read_csv('/etc/passwd'), df.to_csv(path)), expression
# evaluators (pd.eval, df.query), and gateway submodules (np.ctypeslib →
# ctypes). Sandboxed code therefore never touches the raw modules: it gets
# _SandboxModule proxies, and EVERY attribute access (RestrictedPython
# routes them all through _getattr_, and the proxies route direct getattr
# the same way) is checked against the deny-list below. Any attribute that
# resolves to a module is refused unless that module is explicitly allowed.

# Attribute names refused on every object — module functions and instance
# methods alike (df.to_csv is as dangerous as pd.read_csv).
_DENIED_ATTRIBUTES = frozenset({
    # pandas readers (read_pickle deserializes pickles → code execution)
    'read_pickle', 'read_csv', 'read_table', 'read_fwf', 'read_clipboard',
    'read_excel', 'read_json', 'read_html', 'read_xml', 'read_hdf',
    'read_feather', 'read_parquet', 'read_orc', 'read_sas', 'read_spss',
    'read_sql', 'read_sql_query', 'read_sql_table', 'read_gbq', 'read_stata',
    # pandas writers (accept file paths)
    'to_pickle', 'to_csv', 'to_json', 'to_excel', 'to_hdf', 'to_sql',
    'to_parquet', 'to_feather', 'to_stata', 'to_gbq', 'to_clipboard',
    'to_html', 'to_latex', 'to_markdown', 'to_xml',
    # pandas file-handle classes and expression evaluators
    'HDFStore', 'ExcelWriter', 'ExcelFile', 'eval', 'query',
    # numpy file/pickle I/O (ndarray.dump pickles to a file)
    'load', 'save', 'savez', 'savez_compressed', 'loadtxt', 'savetxt',
    'genfromtxt', 'fromregex', 'fromfile', 'tofile', 'memmap',
    'dump', 'dumps',
})

# Modules whose attributes sandboxed code may use (always via a proxy).
_ALLOWED_MODULE_NAMES = frozenset({
    'math', 'numpy', 'numpy.random', 'numpy.linalg', 'numpy.fft', 'pandas',
    'core.strategy',
})


class _SandboxModule:
    """Read-only, policy-filtered view of a module for sandboxed code.

    Both RestrictedPython's _getattr_ and plain getattr (e.g. the
    `from numpy import ...` bytecode, which bypasses _getattr_) end up in
    __getattr__ here, so the deny-list holds on every path.
    """

    __slots__ = ('_sandbox_module',)

    def __init__(self, module):
        object.__setattr__(self, '_sandbox_module', module)

    def __getattr__(self, name):
        return _sandboxed_getattr(
            object.__getattribute__(self, '_sandbox_module'), name)

    def __setattr__(self, name, value):
        raise AttributeError('modules are read-only in the sandbox')

    def __repr__(self):
        module = object.__getattribute__(self, '_sandbox_module')
        return f'<sandboxed module {module.__name__!r}>'


# One proxy per module, cached: attribute access runs in the simulation's
# innermost loop (num_sims × num_years calls), so e.g. np.random must not
# allocate a fresh wrapper on every read.
_MODULE_PROXIES = {}


def _proxy_for_module(module):
    name = module.__name__
    proxy = _MODULE_PROXIES.get(name)
    if proxy is None:
        proxy = _SandboxModule(module)
        _MODULE_PROXIES[name] = proxy
    return proxy


# Optionally, add other safe utilities if needed.
# For example, allowing the 'math' library is generally safe.
import math
_safe_globals['math'] = _proxy_for_module(math)
_safe_globals['np'] = _proxy_for_module(np)
_safe_globals['pd'] = _proxy_for_module(pd)

# Modules strategy code may import. The import machinery resolves __import__
# through __builtins__, so this is enforced by _sandbox_builtins below.
_ALLOWED_IMPORTS = frozenset({'math', 'numpy', 'pandas', 'core.strategy'})


def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level != 0 or name not in _ALLOWED_IMPORTS:
        raise ImportError(
            f"import of '{name}' is not allowed in the sandbox "
            f"(allowed: {sorted(_ALLOWED_IMPORTS)})"
        )
    module = __import__(name, globals, locals, fromlist, level)
    # Wrap in the policy proxy: `from numpy import load` extracts attributes
    # with a direct getattr on the returned module (no _getattr_ involved),
    # so the module object itself must enforce the deny-list.
    return _proxy_for_module(module)


# CRITICAL: exec() injects the REAL builtins module into any globals dict that
# lacks a '__builtins__' key. Pin it to a copy of RestrictedPython's
# safe_builtins (plus the allowlisted __import__) so sandboxed code cannot
# resolve open/eval/exec or arbitrary imports through the backdoor.
_sandbox_builtins = dict(safe_builtins)
_sandbox_builtins['__import__'] = _guarded_import
# safe_builtins is minimal; strategy code legitimately uses these harmless
# extras (they carry no filesystem/process/introspection reach).
import builtins as _real_builtins
for _name in (
    'dict', 'list', 'set', 'frozenset', 'min', 'max', 'sum', 'any', 'all',
    'enumerate', 'map', 'filter', 'reversed', 'iter', 'next',
    'property', 'classmethod', 'staticmethod', 'super', 'object',
):
    _sandbox_builtins[_name] = getattr(_real_builtins, _name)
_safe_globals['__builtins__'] = _sandbox_builtins
# Class creation reads __name__ from globals to set __module__; the real
# builtins module used to supply it ('builtins') before the pin above.
_safe_globals['__name__'] = 'sandboxed_strategy'

def _sandboxed_getattr(obj, name):
    """
    Custom `_getattr_` guard for RestrictedPython.

    By default, RestrictedPython's `safer_getattr` blocks access to any
    attribute starting with an underscore. This custom guard relaxes that rule
    to allow access to single-underscore attributes (e.g., `_my_helper`),
    which is useful for LLM-generated code that uses them for internal helpers.
    It continues to block access to double-underscore attributes (e.g., `__mangled`)
    to maintain a strong security boundary.

    On top of that it enforces the module/attribute policy above: deny-listed
    attribute names raise everywhere, and attributes that resolve to modules
    are only handed out (proxied) when the module is explicitly allowed.
    """
    if name == '__init__':
        pass
    elif name.startswith('__'):
        raise AttributeError(f'Access to double-underscore attributes like "{name}" is not allowed in the sandbox.')
    if name in _DENIED_ATTRIBUTES:
        raise AttributeError(f'"{name}" is not allowed in the sandbox.')
    value = getattr(obj, name)
    if isinstance(value, types.ModuleType):
        if value.__name__ in _ALLOWED_MODULE_NAMES:
            return _proxy_for_module(value)
        raise AttributeError(
            f'module "{value.__name__}" is not accessible in the sandbox.')
    return value

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
        It continues to block double-underscore names to prevent access to mangled attributes,
        and reserves guard-style names (underscore-wrapped, like `_getattr_`,
        `_getitem_`, `_write_`) so sandboxed code can never shadow or rebind
        the RestrictedPython guards its own transformed code calls.
        """
        if name is None:
            return node

        if name.startswith('__'):
            if not allow_magic_methods:
                logging.error(f"DEBUG SANDBOX: Blocking name '{name}' at line {getattr(node, 'lineno', '?')}")
                self.error(node, f'"{name}" is an invalid variable name because it starts with "__".')
        elif name.startswith('_') and name.endswith('_'):
            self.error(node, f'"{name}" is a reserved sandbox guard name pattern (underscore-wrapped).')
        return node

    def visit_Global(self, node):
        """Forbid `global`: the exec globals hold the sandbox guards, and a
        `global _getattr_ = ...` rebinding would neuter them for the rest of
        the execution. Strategies have no legitimate use for it."""
        self.error(node, 'global statements are not allowed in the sandbox.')
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

    def reset(self):
        # Forward to the wrapped strategy — without this, the engine's
        # between-paths reset() hit only the wrapper, and instance state
        # (retirement flags, high-water marks) leaked from one simulated
        # path into the next: the first path that triggered a state change
        # poisoned every path after it.
        self.sandboxed_strategy.reset()

def _slugify_to_classname(text: str) -> str:
    """Converts a string into a valid Python class name."""
    # Remove invalid characters, then capitalize each word and join them.
    text = re.sub(r'[^a-zA-Z0-9_ ]', '', text)
    return "".join(word.capitalize() for word in text.split())

def _validate_strategy_class(strategy_class, strict_category=False):
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
        # Strict mode is opt-in (agent-generated code): stored strategies keep
        # the historical tolerant behavior (coerced to HYBRID downstream).
        valid_categories = {'WITHDRAWAL_ONLY', 'CONTRIBUTION_ONLY', 'HYBRID'}
        try:
            category = instance.evaluation_category()
        except Exception as e:
            if strict_category:
                raise ValueError(f"evaluation_category() raised: {e}")
            logging.warning(f"evaluation_category() raised ({e}); tolerating for stored strategy.")
            category = None
        if category is not None and category not in valid_categories:
            if strict_category:
                raise ValueError(f"evaluation_category() returned '{category}'. Valid options are: {valid_categories}")
            logging.warning(f"evaluation_category() returned invalid '{category}'; will be coerced downstream.")

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


# --- Resource-limited validation -------------------------------------------
# The dry run in _validate_strategy_class executes the untrusted code's
# methods. RestrictedPython bounds WHAT the code can reach, not how long it
# runs or how much memory it takes — a `while True:` or a giant allocation
# would otherwise hang or OOM whichever process is validating (API thread or
# worker). So the whole compile+exec+dry-run first happens in a throwaway
# spawn subprocess under a wall-clock timeout, an RLIMIT_CPU, and an
# RLIMIT_AS cap (best-effort; not enforceable on macOS). Only code that
# passes within limits is then executed in the calling process.
#
# Residual risk (documented in CODE_REVIEW R1.2): code whose runaway path
# only triggers under later simulation-time conditions passes this gate; the
# job-level timeout is the backstop for that.

def _validation_timeout_seconds() -> float:
    return float(os.getenv('SANDBOX_VALIDATION_TIMEOUT_SECONDS', '20'))


def _validation_worker(code_string, strategy_class_name, strict_category, queue):
    """Runs in a spawn subprocess: apply rlimits, then compile+validate."""
    try:
        try:
            import resource

            cpu_budget = max(2, int(_validation_timeout_seconds()) + 5)
            try:
                resource.setrlimit(resource.RLIMIT_CPU, (cpu_budget, cpu_budget))
            except (ValueError, OSError):
                pass
            try:
                memory_mb = int(os.getenv('SANDBOX_VALIDATION_MEMORY_MB', '1024'))
            except ValueError:
                memory_mb = 1024  # a bad env var must not fail every validation
            memory_bytes = memory_mb * 1024 * 1024
            try:
                resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
            except (ValueError, OSError):
                pass  # macOS does not reliably support RLIMIT_AS
        except ImportError:
            pass
        execute_strategy_code(
            code_string, strategy_class_name,
            strict_category=strict_category, isolate=False)
        queue.put(('ok', None, None))
    except BaseException as e:  # noqa: BLE001 — report MemoryError etc. too
        import traceback

        # The child has no configured logging; ship the traceback back so the
        # parent can log why the dry run failed.
        queue.put(('error', f'{type(e).__name__}: {e}',
                   traceback.format_exc(limit=20)[-4000:]))


def _validate_in_subprocess(code_string, strategy_class_name, strict_category):
    """Dry-run the untrusted code in a resource-limited subprocess.

    Raises ValueError on timeout or when the child dies without reporting
    (e.g. killed by the kernel on memory exhaustion).
    """
    ctx = multiprocessing.get_context('spawn')
    queue = ctx.Queue()
    proc = ctx.Process(
        target=_validation_worker,
        args=(code_string, strategy_class_name, strict_category, queue),
        daemon=True,
    )
    proc.start()
    proc.join(_validation_timeout_seconds())
    try:
        if proc.is_alive():
            proc.terminate()
            proc.join(2)
            if proc.is_alive():
                proc.kill()
                proc.join(2)
            raise ValueError(
                "Strategy validation timed out — the code appears to run "
                "indefinitely (e.g. an infinite loop) and was rejected.")
        try:
            status, detail, child_traceback = queue.get(timeout=5)
        except Exception:
            raise ValueError(
                "Strategy validation crashed (likely exceeded the sandbox "
                "memory limit) and was rejected.")
        if status != 'ok':
            if child_traceback:
                logging.error(
                    "Sandbox validation failed in subprocess:\n%s", child_traceback)
            raise ValueError(f"Strategy validation failed: {detail}")
    finally:
        queue.close()


def execute_strategy_code(code_string: str, strategy_class_name: str = "CustomStrategy", strict_category=False, isolate=True):
    """
    Safely compiles and executes a string of Python code to define a custom strategy class.

    This function uses RestrictedPython to create a sandboxed environment, preventing
    the execution of unsafe code (e.g., file I/O, network access). Unless
    isolate=False, the compile+dry-run first happens in a resource-limited
    subprocess so hangs and memory bombs are rejected without harming this
    process (isolate=False is for the subprocess itself and for callers that
    already run inside an isolated context).

    Args:
        code_string (str): The Python code for the strategy class, as generated by an LLM.
        strategy_class_name (str): The expected name of the strategy class in the code.

    Returns:
        The dynamically created strategy class if successful and safe, otherwise None.
    """
    try:
        logging.info(f"Attempting to execute sandboxed code for strategy: {strategy_class_name}")

        if isolate:
            _validate_in_subprocess(code_string, strategy_class_name, strict_category)

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

        # 2. Prepare a per-call namespace. The globals are a fresh shallow
        # copy: exec writes (and any runtime rebinding trick that slips past
        # the compile-time bans on `global` and guard-style names) must never
        # mutate the shared template that later strategies will use.
        local_namespace = {}
        exec_globals = dict(_safe_globals)

        # 3. Execute the compiled code. The result will populate local_namespace.
        exec(byte_code, exec_globals, local_namespace)

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

        # 5. Dry-run validation to catch runtime errors like KeyErrors.
        # When isolate=True the resource-limited subprocess already ran this
        # exact dry run — repeating it here would execute the untrusted
        # methods a second time with NO limits (and double the cost), so it
        # only runs for isolate=False (i.e. inside the guarded child).
        if not isolate:
            _validate_strategy_class(strategy_class, strict_category=strict_category)

        logging.info(f"Successfully executed and validated sandboxed strategy class: {strategy_class_name}")
        # Return the user's strategy class. The calling code is responsible for wrapping it.
        return strategy_class
    except Exception as e:
        logging.error(f"An error occurred during sandboxed execution: {e}", exc_info=True)
        # Re-raise the exception so it can be caught and displayed by the UI.
        raise