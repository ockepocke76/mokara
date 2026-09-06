"""
Centralized radar chart data preparation for category-aware metrics.
Filters out metrics that are not applicable (None) for specific strategy types.
"""

def prepare_radar_chart_data(evaluation_data, metric_source='METRIC_REGISTRY', profile_weights=None):
    """
    Prepare radar chart data with category-aware filtering.
    
    Args:
        evaluation_data: Dict containing strategy evaluation scores
        metric_source: 'METRIC_REGISTRY' or 'METRIC_WEIGHTS' (for backwards compatibility)
        profile_weights: Optional dict of {metric_key: weight} for custom weighting profiles
    
    Returns:
        tuple: (categories, values, active_metrics) where:
            - categories: List of metric names (applicable only)
            - values: List of metric scores (applicable only)
            - active_metrics: List of dicts with 'name', 'key', 'weight'
    """
    if profile_weights:
        # Custom profile weights (e.g., from leaderboard)
        from core.strategy_evaluation import METRIC_REGISTRY
        
        # Exclude deprecated metrics
        excluded = {'adequacy_score', 'usability_score'}
        
        active_metrics = [
            {
                'name': METRIC_REGISTRY[k].name,
                'key': k,
                'weight': w
            }
            for k, w in profile_weights.items()
            if k in METRIC_REGISTRY and k not in excluded
        ]
    elif metric_source == 'METRIC_REGISTRY':
        from core.strategy_evaluation import METRIC_REGISTRY
        
        # Build list of all metrics with their info
        active_metrics = [
            {
                'name': metric.name,
                'key': key,
                'weight': metric.weight
            }
            for key, metric in METRIC_REGISTRY.items()
            if metric.weight > 0  # Only include metrics with non-zero weight
        ]
    else:
        # Legacy support for METRIC_WEIGHTS
        from core.strategy_evaluation import METRIC_WEIGHTS
        active_metrics = [
            {'name': v['name'], 'key': k, 'weight': v['weight']}
            for k, v in METRIC_WEIGHTS.items()
            if v['weight'] > 0
        ]
    
    # Filter out metrics where the score is None (not applicable)
    applicable_metrics = []
    applicable_values = []
    
    for metric in active_metrics:
        score = evaluation_data.get(metric['key'])
        # Only include if score is not None (metric is applicable to this strategy)
        if score is not None:
            applicable_metrics.append(metric)
            applicable_values.append(score)
    
    # Extract categories from applicable metrics
    categories = [m['name'] for m in applicable_metrics]
    
    return categories, applicable_values, applicable_metrics


def _weight_to_color(weight):
    """
    Map metric weight to marker color intensity.
    
    Args:
        weight: Float between 0.0 and 1.0 representing metric weight
        
    Returns:
        RGBA color string (darker = higher weight, lighter = lower/informational)
    """
    # Gradient calibrated so 40%+ weight shows dark blue/black
    if weight >= 0.40:  # 40%+ weight (very important)
        return 'rgba(30, 50, 100, 1.0)'  # Very dark blue (almost black)
    elif weight >= 0.20:  # 20-40% weight (important)
        return 'rgba(60, 95, 150, 0.9)'  # Dark blue
    elif weight >= 0.10:  # 10-20% weight (moderate)
        return 'rgba(90, 130, 180, 0.75)'  # Medium blue
    elif weight >= 0.05:  # 5-10% weight (low priority)
        return 'rgba(120, 160, 200, 0.6)'  # Light-medium blue
    elif weight > 0:  # 0-5% weight (minimal)
        return 'rgba(150, 180, 210, 0.45)'  # Light blue
    else:  # 0% weight (informational only)
        return 'rgba(180, 180, 180, 0.6)'  # Light gray


def create_radar_chart(evaluation_data, metric_source='METRIC_REGISTRY', profile_weights=None, 
                       strategy_name=None, excellence_score=None, title=None, height=400):
    """
    Create a radar chart with weight-based marker coloring.
    
    Args:
        evaluation_data: Dict containing strategy evaluation scores
        metric_source: 'METRIC_REGISTRY' or 'METRIC_WEIGHTS'
        profile_weights: Optional dict of {metric_key: weight} for custom profiles
        strategy_name: Optional strategy name for legend
        excellence_score: Optional excellence score to show in title
        title: Optional custom title (overrides excellence_score title)
        height: Chart height in pixels
        
    Returns:
        Plotly Figure object or None if no applicable metrics
    """
    import plotly.graph_objects as go
    
    # Prepare data
    categories, values, active_metrics = prepare_radar_chart_data(
        evaluation_data, 
        metric_source=metric_source,
        profile_weights=profile_weights
    )
    
    # Return None if no applicable metrics
    if not categories:
        return None
    
    # Close the loop for radar chart
    values_closed = values + [values[0]]
    categories_closed = categories + [categories[0]]
    
    # Calculate marker colors based on weights
    marker_colors = [_weight_to_color(m['weight']) for m in active_metrics]
    marker_colors_closed = marker_colors + [marker_colors[0]]  # Close the loop
    
    # Create figure
    fig = go.Figure()
    
    fig.add_trace(go.Scatterpolar(
        r=values_closed,
        theta=categories_closed,
        fill='toself',
        mode='lines+markers',  # Show both lines and markers
        name=strategy_name or 'Strategy',
        line_color='#4C78A8',
        fillcolor='rgba(76, 120, 168, 0.3)',
        marker=dict(
            size=8,  # Visible marker size
            color=marker_colors_closed,  # Weight-based colors
            line=dict(color='white', width=1.5)  # White outline for visibility
        )
    ))
    
    # Build title text
    if title:
        title_text = title
    elif excellence_score is not None:
        title_text = f"<b>Excellence Score: {excellence_score:.1f}/100</b>"
    else:
        title_text = None
    
    # Layout configuration
    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 100],
                showticklabels=True,
                tickfont=dict(size=10)
            )
        ),
        showlegend=False,
        title=dict(
            text=title_text,
            x=0.5,
            xanchor='center'
        ) if title_text else None,
        height=height,
        margin=dict(t=60, b=40, l=60, r=60)
    )
    
    return fig
