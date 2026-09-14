"""
Executive Summary Visualizations Module

This module creates engaging, modern visualizations for the executive summary
section of simulation reports. Inspired by game development UI/UX and modern
financial dashboards, these visualizations make complex data instantly digestible.

Features:
- Multi-dimensional bubble charts showing risk/reward/value
- Interactive Plotly charts with premium styling
- Glass morphism effects and vibrant gradients
- Responsive, mobile-friendly designs
"""

import plotly.graph_objects as go
import plotly.express as px
from typing import Dict, Any
import numpy as np
from reporting.color_scheme import ExecutiveColors
import base64
import io



def create_verdict_traffic_light(stats: Dict[str, Any], mobile: bool = False) -> go.Figure:
    """
    Creates a 3-gauge executive dashboard showing key FIRE metrics.
    
    Gauges:
    1. Success Rate (Portfolio Survival) - 0-100%
    2. Years of Spending Left (Longevity) - 0-50 years
    3. Real Profit Chance (Beating Inflation) - 0-100%
    
    Args:
        stats: Final statistics dictionary
        mobile: If True, use smaller fonts for mobile display
        
    Returns:
        Plotly Figure object with 3-gauge dashboard
    """
    from plotly.subplots import make_subplots
    
    # Font sizes - smaller on mobile
    number_font_size = 16 if mobile else 24
    title_font_size = 11 if mobile else 16
    verdict_font_size = 12 if mobile else 18
    
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
        horizontal_spacing=0.05
    )
    
    # --- GAUGE 1: Success Rate ---
    if success_rate >= 95:
        verdict_1 = "LOW RISK"
        color_1 = ExecutiveColors.VERDICT_GREEN
    elif success_rate >= 85:
        verdict_1 = "MODERATE"
        color_1 = ExecutiveColors.VERDICT_YELLOW
    else:
        verdict_1 = "HIGH RISK"
        color_1 = ExecutiveColors.VERDICT_RED
    
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=success_rate,
        number={'suffix': "%", 'font': {'size': number_font_size, 'color': color_1, 'family': 'Arial Black'}},
        title={'text': "<b>Success Rate</b>", 'font': {'size': title_font_size}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 2, 'tickcolor': "#9CA3AF"},
            'bar': {'color': color_1, 'thickness': 0.25},
            'bgcolor': "white",
            'borderwidth': 0,
            'steps': [
                {'range': [0, 85], 'color': ExecutiveColors.GAUGE_ZONE_RED},
                {'range': [85, 95], 'color': ExecutiveColors.GAUGE_ZONE_YELLOW},
                {'range': [95, 100], 'color': ExecutiveColors.GAUGE_ZONE_GREEN}
            ]
        },
        domain={'x': [0, 0.32], 'y': [0.3, 1]}
    ), row=1, col=1)
    
    # --- GAUGE 2: Years of Spending Left ---
    if years_left >= 30:
        verdict_2 = "EXCELLENT"
        color_2 = ExecutiveColors.VERDICT_GREEN
    elif years_left >= 20:
        verdict_2 = "ADEQUATE"
        color_2 = ExecutiveColors.VERDICT_YELLOW
    else:
        verdict_2 = "LIMITED"
        color_2 = ExecutiveColors.VERDICT_RED
    
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=years_left,
        number={'suffix': " yrs", 'font': {'size': number_font_size, 'color': color_2, 'family': 'Arial Black'}},
        title={'text': "<b>Years Remaining</b>", 'font': {'size': title_font_size}},
        gauge={
            'axis': {'range': [0, 50], 'tickwidth': 2, 'tickcolor': "#9CA3AF"},
            'bar': {'color': color_2, 'thickness': 0.25},
            'bgcolor': "white",
            'borderwidth': 0,
            'steps': [
                {'range': [0, 20], 'color': ExecutiveColors.GAUGE_ZONE_RED},
                {'range': [20, 30], 'color': ExecutiveColors.GAUGE_ZONE_YELLOW},
                {'range': [30, 50], 'color': ExecutiveColors.GAUGE_ZONE_GREEN}
            ]
        },
        domain={'x': [0.34, 0.66], 'y': [0.3, 1]}
    ), row=1, col=2)
    
    # --- GAUGE 3: Real Profit Chance ---
    if real_profit_chance >= 75:
        verdict_3 = "STRONG"
        color_3 = ExecutiveColors.VERDICT_GREEN
    elif real_profit_chance >= 50:
        verdict_3 = "MODERATE"
        color_3 = ExecutiveColors.VERDICT_YELLOW
    else:
        verdict_3 = "WEAK"
        color_3 = ExecutiveColors.VERDICT_RED
    
    fig.add_trace(go.Indicator(
        mode="gauge+number",
        value=real_profit_chance,
        number={'suffix': "%", 'font': {'size': number_font_size, 'color': color_3, 'family': 'Arial Black'}},
        title={'text': "<b>Real Profit</b>", 'font': {'size': title_font_size}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 2, 'tickcolor': "#9CA3AF"},
            'bar': {'color': color_3, 'thickness': 0.25},
            'bgcolor': "white",
            'borderwidth': 0,
            'steps': [
                {'range': [0, 50], 'color': ExecutiveColors.GAUGE_ZONE_RED},
                {'range': [50, 75], 'color': ExecutiveColors.GAUGE_ZONE_YELLOW},
                {'range': [75, 100], 'color': ExecutiveColors.GAUGE_ZONE_GREEN}
            ]
        },
        domain={'x': [0.68, 1.0], 'y': [0.3, 1]}
    ), row=1, col=3)
    
    # Add verdict text below each gauge
    fig.add_annotation(
        text=f"<b>{verdict_1}</b>",
        x=0.16, y=0.15,
        xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=verdict_font_size, color=color_1, family="Arial Black"),
        xanchor='center'
    )
    
    fig.add_annotation(
        text=f"<b>{verdict_2}</b>",
        x=0.5, y=0.15,
        xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=verdict_font_size, color=color_2, family="Arial Black"),
        xanchor='center'
    )
    
    fig.add_annotation(
        text=f"<b>{verdict_3}</b>",
        x=0.84, y=0.15,
        xref="paper", yref="paper",
        showarrow=False,
        font=dict(size=verdict_font_size, color=color_3, family="Arial Black"),
        xanchor='center'
    )
    
    fig.update_layout(
        title=dict(
            text="<b>Portfolio Health Dashboard</b>",
            font=dict(size=20, color='#1F2937'),
            x=0.5,
            xanchor='center',
            y=0.98
        ),
        height=300,
        margin=dict(l=20, r=20, t=50, b=20),
        paper_bgcolor='white',
        font=dict(family='Arial, sans-serif', color='#374151')
    )
    
    return fig
