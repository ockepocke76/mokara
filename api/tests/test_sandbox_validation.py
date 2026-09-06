import pytest
from pathlib import Path
import sys
import re

# Add the project root to the Python path to allow for absolute imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.sandbox import execute_strategy_code, _slugify_to_classname

# Define the directory where AI-generated code snippets are stored
SNIPPET_DIR_NAME = "ai_strategy_snippets"

def pytest_generate_tests(metafunc):
    if "filepath" in metafunc.fixturenames:
        rootdir = metafunc.config.rootpath
        snippet_path = rootdir / "tests" / SNIPPET_DIR_NAME
        if not snippet_path.exists():
            filepaths = []
        else:
            # Collect both .py and .txt files for testing
            filepaths = list(snippet_path.glob("*.py")) + list(snippet_path.glob("*.txt"))
        # Create more descriptive test IDs
        ids = [p.name for p in filepaths]
        metafunc.parametrize("filepath", filepaths, ids=ids)



def test_ai_strategy_validation(filepath):
    """
    Tests the validation of AI-generated strategy code from files.

    - If a filename ends with '_pass.py' or '_pass.txt', the code is expected to be valid.
    - If a filename ends with '_fail.py' or '_fail.txt', the code is expected to raise an exception.
    """
    # Extract a class name from the file content
    with open(filepath, 'r') as f:
        code_string = f.read()
    
    # Normalize filepath name to check suffix regardless of extension
    filename_stem = filepath.stem  # filename without extension
    filename = filepath.name
    
    class_name_match = re.search(r"class\s+([\w_]+)\(BaseStrategy\)", code_string)
    if not class_name_match:
        if filename_stem.endswith("_fail"):
            return # Pass the test - expected to fail, and it doesn't even have a proper class
        else:
            pytest.fail(f"Could not find a class inheriting from BaseStrategy in {filename}")
    else:
        class_name = class_name_match.group(1)

    if filename_stem.endswith("_pass"):
        try:
            strategy_class = execute_strategy_code(code_string, class_name)
            assert strategy_class is not None, f"Expected code in {filename} to pass validation, but it failed."
            assert strategy_class.__name__ == class_name
        except Exception as e:
            pytest.fail(f"Code in {filename} was expected to pass validation but raised an exception: {e}")

    elif filename_stem.endswith("_fail"):
        # We can be more specific about the expected exceptions for different failure modes.
        # This assumes your enhanced `execute_strategy_code` will perform a "dry run"
        # that triggers runtime errors.
        expected_exception = Exception # Default broad exception
        if "key_error" in filename:
            expected_exception = KeyError
        elif "disallowed_import" in filename:
            # Assuming the sandbox raises a ValueError for disallowed imports.
            # Adjust this to the actual exception type your sandbox raises.
            expected_exception = ValueError
        elif "syntax_error" in filename:
            expected_exception = SyntaxError
        elif "missing_method" in filename:
            expected_exception = TypeError

        with pytest.raises(expected_exception) as excinfo:
            execute_strategy_code(code_string, class_name)
        assert excinfo.value is not None, f"Expected code in {filename} to fail with {expected_exception.__name__}, but it passed."
        print(f"Successfully caught expected exception for {filename}: {excinfo.type.__name__}")

    else:
        pytest.skip(f"Skipping file with unknown suffix: {filename}")