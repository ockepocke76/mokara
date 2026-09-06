"""
Helper functions for generating strategy evaluation charts for PDF reports.
"""

import os
import logging
from io import BytesIO

try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-interactive backend
    import matplotlib.pyplot as plt
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logging.warning("Matplotlib not available - radar charts will not be generated for PDF")


def generate_evaluation_radar_chart_png(strategy_name: str, evaluation_data: dict, output_path: str = None) -> BytesIO:
    """
    Generate a radar chart PNG for strategy evaluation metrics.
    
    Args:
        strategy_name: Name of the strategy
        evaluation_data: Dictionary with metric scores (pv_score, robustness_score, etc.)
        output_path: Optional file path to save PNG. If None, returns BytesIO buffer.
        
    Returns:
        BytesIO buffer containing the PNG image, or path string if output_path provided.
    """
    if not MATPLOTLIB_AVAILABLE:
        logging.error("Cannot generate radar chart: matplotlib not available")
        return None
    
    from core.strategy_evaluation import METRIC_WEIGHTS
    
    # Build metrics from central definition (only active ones)
    active_metrics = [
        {'name': v['name'], 'key': k, 'weight': v['weight']}
        for k, v in METRIC_WEIGHTS.items()
        if v['weight'] > 0
    ]
    
    categories = [m['name'] for m in active_metrics]
    values = [evaluation_data.get(m['key'], 0) for m in active_metrics]
    
    # Number of variables
    N = len(categories)
    
    # Compute angle for each category
    angles = [n / float(N) * 2 * np.pi for n in range(N)]
    angles += angles[:1]  # Complete the loop
    values += values[:1]  # Complete the loop
    
    # Create figure
    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
    
    # Draw the polygon
    ax.fill(angles, values, color='#4C78A8', alpha=0.3)
    ax.plot(angles, values, color='#4C78A8', linewidth=2)
    
    # Add category labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, size=9)
    
    # Set y-axis range
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(['20', '40', '60', '80', '100'], size=8)
    
    # Add title with excellence score
    excellence_score = evaluation_data.get('excellence_score', 0)
    ax.set_title(f'{strategy_name}\nExcellence Score: {excellence_score:.1f}/100', 
                 size=12, fontweight='bold', pad=20)
    
    plt.tight_layout()
    
    # Save to buffer or file
    if output_path:
        plt.savefig(output_path, format='png', dpi=150, bbox_inches='tight', 
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        return output_path
    else:
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=150, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        buffer.seek(0)
        return buffer


def get_evaluation_for_strategy(strategy_name: str, class_name: str = None, git_commit_sha: str = None, clone_source_commit_sha: str = None) -> dict:
    """
    Fetch evaluation data for a strategy from the leaderboard or by commit SHA.
    
    Args:
        strategy_name: Display name of the strategy (e.g., "Trinity", "Get Rich Stay Rich")
        class_name: Optional class name for custom strategies
        git_commit_sha: Optional SHA of the specific strategy version
        clone_source_commit_sha: Optional fallback SHA of the parent strategy (for unedited clones)
        
    Returns:
        Dictionary with evaluation data or None if not found
    """
    from db.database import db
    
    # 1. Precise lookup by SHA (Primary Link)
    if git_commit_sha or clone_source_commit_sha:
        evaluation = db.get_strategy_evaluation(git_commit_sha, lookup_fallback_sha=clone_source_commit_sha)
        if evaluation:
            return evaluation
    
    # 2. Legacy lookup by Name/Class (Fallback for built-in or older entries)
    leaderboard_data = db.get_leaderboard(limit=100)
    
    for entry in leaderboard_data:
        if entry['strategy_name'].lower() == strategy_name.lower():
            return entry
        # Also check class_name for custom strategies
        if class_name and entry.get('class_name', '').lower() == class_name.lower():
            return entry
    
    return None
