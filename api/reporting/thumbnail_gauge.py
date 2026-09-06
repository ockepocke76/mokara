from typing import Dict, Any
import plotly.graph_objects as go
from reporting.color_scheme import ExecutiveColors


def create_thumbnail_gauge_dashboard(stats: Dict[str, Any]) -> go.Figure:
    """
    Creates a compact thumbnail version of the 3-gauge dashboard for simulation listings.
    Returns a small Plotly figure (120px height) for quick preview.
    
    Args:
        stats: Final statistics dictionary
        
    Returns:
        Plotly Figure object with compact 3-gauge dashboard
    """
    from plotly.subplots import make_subplots
    
    # Extract metrics
    success_rate = stats.get('success_rate', 0.0) * 100
    years_left = stats.get('median_years_of_spending_left')
    real_profit_chance = stats.get('chance_of_real_profit', 0.0) * 100
    
    # Handle None for contribution-only strategies
    if years_left is None or years_left == 'N/A':
        years_left = 0
    
    # Create subplots for 3 gauges side-by-side
    fig = make_subplots(
        rows=1, cols=3,
        specs=[[{'type': 'indicator'}, {'type': 'indicator'}, {'type': 'indicator'}]],
        horizontal_spacing=0.08
    )
    
    # Determine colors
    color_1 = ExecutiveColors.VERDICT_GREEN if success_rate >= 95 else (ExecutiveColors.VERDICT_YELLOW if success_rate >= 85 else ExecutiveColors.VERDICT_RED)
    color_2 = ExecutiveColors.VERDICT_GREEN if years_left >= 30 else (ExecutiveColors.VERDICT_YELLOW if years_left >= 20 else ExecutiveColors.VERDICT_RED)
    color_3 = ExecutiveColors.VERDICT_GREEN if real_profit_chance >= 75 else (ExecutiveColors.VERDICT_YELLOW if real_profit_chance >= 50 else ExecutiveColors.VERDICT_RED)
    
    # Add gauges with minimal styling for compact display
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=success_rate,
        number={'suffix': "%", 'font': {'size': 16, 'color': color_1}},
        gauge={
            'axis': {'range': [0, 100], 'visible': False},
            'bar': {'color': color_1, 'thickness': 0.15},
            'bgcolor': "white",
            'borderwidth': 0,
            'steps': [
                {'range': [0, 85], 'color': '#FEE2E2'},
                {'range': [85, 95], 'color': '#FEF3C7'},
                {'range': [95, 100], 'color': '#D1FAE5'}
            ]
        }
    ), row=1, col=1)
    
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=years_left,
        number={'suffix': "y", 'font': {'size': 16, 'color': color_2}},
        gauge={
            'axis': {'range': [0, 50], 'visible': False},
            'bar': {'color': color_2, 'thickness': 0.15},
            'bgcolor': "white",
            'borderwidth': 0,
            'steps': [
                {'range': [0, 20], 'color': '#FEE2E2'},
                {'range': [20, 30], 'color': '#FEF3C7'},
                {'range': [30, 50], 'color': '#D1FAE5'}
            ]
        }
    ), row=1, col=2)
    
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=real_profit_chance,
        number={'suffix': "%", 'font': {'size': 16, 'color': color_3}},
        gauge={
            'axis': {'range': [0, 100], 'visible': False},
            'bar': {'color': color_3, 'thickness': 0.15},
            'bgcolor': "white",
            'borderwidth': 0,
            'steps': [
                {'range': [0, 50], 'color': '#FEE2E2'},
                {'range': [50, 75], 'color': '#FEF3C7'},
                {'range': [75, 100], 'color': '#D1FAE5'}
            ]
        }
    ), row=1, col=3)
    
    fig.update_layout(
        height=120,
        margin=dict(l=2, r=2, t=5, b=2),
        paper_bgcolor='white',
        showlegend=False
    )
    
    return fig
