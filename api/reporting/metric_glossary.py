"""
Glossary tooltip lookup utilities.

This module provides direct lookups from metric labels to glossary definitions.
No mapping needed - metric labels in tables should match glossary term names exactly.
"""

import logging
from typing import Optional, List, Tuple, Dict


def get_metric_tooltip(label: str, warn_if_missing: bool = True) -> Optional[str]:
    """
    Retrieves the tooltip text for a metric label directly from the glossary.
    
    Args:
        label: The metric label as displayed in tables (should match glossary term exactly)
        warn_if_missing: If True, logs a warning if no tooltip is found
        
    Returns:
        The tooltip text from the glossary, or None if not found
    """
    from reporting.content import get_glossary_data
    
    # Direct lookup in glossary
    glossary = get_glossary_data()
    for category, terms in glossary.items():
        if label in terms:
            return terms[label]
    
    # Not found
    if warn_if_missing:
        logging.warning(
            f"No glossary entry found for metric label: '{label}'. "
            f"Either add it to the glossary in reporting/content.py, "
            f"or update the metric label to match an existing glossary term."
        )
    return None


def validate_metric_tooltips(metrics: List[dict]) -> Tuple[int, List[str]]:
    """
    Validates that all metrics in a table have glossary entries.
    
    Args:
        metrics: List of metric dicts with 'label' keys
        
    Returns:
        Tuple of (found_count, missing_labels)
    """
    missing_labels = []
    found_count = 0
    
    for metric in metrics:
        label = metric.get('label', '')
        if not label:
            continue
            
        tooltip = get_metric_tooltip(label, warn_if_missing=False)
        if tooltip:
            found_count += 1
        else:
            missing_labels.append(label)
    
    return found_count, missing_labels


def list_all_glossary_terms() -> Dict[str, List[str]]:
    """
    Returns all available glossary terms organized by category.
    Useful for developers to see what terms are available.
    
    Returns:
        Dict mapping category names to lists of term names
    """
    from reporting.content import get_glossary_data
    
    glossary = get_glossary_data()
    return {category: list(terms.keys()) for category, terms in glossary.items()}


def print_glossary_terms():
    """
    Pretty-prints all available glossary terms.
    Useful for seeing what metric labels you can use.
    """
    terms_by_category = list_all_glossary_terms()
    
    print("=" * 80)
    print("AVAILABLE GLOSSARY TERMS")
    print("=" * 80)
    print()
    print("Use these exact names as 'label' values in your metric tables.")
    print("Tooltips will be automatically added from the glossary.")
    print()
    
    for category, terms in terms_by_category.items():
        print(f"\n{category}")
        print("-" * len(category))
        for term in sorted(terms):
            print(f"  • {term}")
    
    print()
    print("=" * 80)


def find_similar_glossary_terms(label: str, max_results: int = 5) -> List[str]:
    """
    Finds glossary terms similar to the given label.
    Useful for suggesting corrections when a metric label doesn't have a tooltip.
    
    Args:
        label: The metric label to find similar terms for
        max_results: Maximum number of suggestions to return
        
    Returns:
        List of similar glossary term names
    """
    from difflib import get_close_matches
    from reporting.content import get_glossary_data
    
    # Get all glossary term names
    glossary = get_glossary_data()
    all_terms = []
    for terms in glossary.values():
        all_terms.extend(terms.keys())
    
    # Find close matches
    matches = get_close_matches(label, all_terms, n=max_results, cutoff=0.6)
    return matches
