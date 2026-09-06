
import hashlib
import os
from pathlib import Path

# Define the logical components and the files/directories that belong to them.
# This is the single source of truth for what constitutes a change in a component.
COMPONENT_MAP = {
    "Simulation Engine": ["simulation.py"],
    "Core Statistics": ["core/stats.py"],
    "Portfolio Logic": ["core/portfolio.py"],
    "Strategy Logic": ["core/strategy.py", "core/sandbox.py", "core/strategy_get_rich_stay_rich.py"],
    "Data Handling": ["core/data.py"],
    "Shared Logic": ["core/shared_logic.py"],
}

def get_component_hashes():
    """
    Calculates a dictionary of SHA256 hashes for each defined logical component.

    Returns:
        dict: A dictionary where keys are component names and values are their hashes.
    """
    project_root = Path(__file__).parent
    hashes = {}

    for component, paths in COMPONENT_MAP.items():
        component_content = b""
        for path_str in paths:
            full_path = project_root / path_str
            if full_path.is_file():
                try:
                    component_content += full_path.read_bytes()
                except FileNotFoundError:
                    # Handle case where a file might not exist
                    pass
            elif full_path.is_dir():
                # Recursively read all .py files in the directory
                for py_file in sorted(full_path.rglob("*.py")):
                    try:
                        component_content += py_file.read_bytes()
                    except FileNotFoundError:
                        pass
        
        # Create a SHA256 hash of the concatenated content
        hasher = hashlib.sha256()
        hasher.update(component_content)
        hashes[component] = hasher.hexdigest()

    return hashes
