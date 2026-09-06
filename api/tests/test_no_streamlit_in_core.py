"""
Guardrail: non-UI layers must never import streamlit (directly or transitively).

Runs in a subprocess with an import hook that raises on any `streamlit`
import, then imports every module under the non-UI packages. A regression
anywhere in the import graph of core/, db/, services/, utils/, reporting/
or background_tasks.py fails this test with the offending module named.
"""
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

CHECK_SCRIPT = r"""
import importlib
import pkgutil
import sys

class StreamlitBlocker:
    def find_spec(self, name, path=None, target=None):
        if name == 'streamlit' or name.startswith('streamlit.'):
            raise ImportError(
                f"BLOCKED import of {name!r}: non-UI code must not import streamlit"
            )
        return None

sys.meta_path.insert(0, StreamlitBlocker())

PACKAGES = ['core', 'db', 'services', 'utils', 'reporting']
MODULES = ['background_tasks']

failures = []

def try_import(module_name):
    try:
        importlib.import_module(module_name)
    except Exception as e:
        failures.append(f"{module_name}: {type(e).__name__}: {e}")

for pkg_name in PACKAGES:
    try:
        pkg = importlib.import_module(pkg_name)
    except Exception as e:
        failures.append(f"{pkg_name}: {type(e).__name__}: {e}")
        continue
    for info in pkgutil.walk_packages(pkg.__path__, prefix=pkg_name + '.'):
        try_import(info.name)

for mod in MODULES:
    try_import(mod)

if failures:
    print('STREAMLIT-FREE CHECK FAILED:')
    for f in failures:
        print('  ' + f)
    sys.exit(1)
print('OK')
"""


def test_non_ui_layers_import_without_streamlit():
    result = subprocess.run(
        [sys.executable, '-c', CHECK_SCRIPT],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"Non-UI code imports streamlit (or fails to import):\n"
        f"{result.stdout}\n{result.stderr}"
    )
