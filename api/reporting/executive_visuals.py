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



def create_financial_health_bubble(params: Dict[str, Any], stats: Dict[str, Any], currency: str = 'SEK') -> go.Figure:
    """
    Creates a multi-dimensional bubble chart showing the financial health of the simulation.
    
    This flagship visualization combines multiple key metrics into a single, intuitive chart:
    - X-axis: Return on Investment (%)
    - Y-axis: Success Rate (%)
    - Bubble Size: Final Portfolio Value
    - Bubble Color: Risk Level (inverse of success rate, or chance of ruin)
    
    Args:
        params: Simulation parameters dictionary
        stats: Final statistics dictionary
        currency: Currency code for formatting
        
    Returns:
        Plotly Figure object with the bubble chart
    """
    from core.currency_config import format_currency_amount
    
    # Extract key metrics
    initial_investment = params.get('initial_investment', 0)
    median_final_net_worth = stats.get('median_final_net_worth', 0)
    total_withdrawn = stats.get('median_total_withdrawn', 0)
    total_contributed = stats.get('median_total_contributions', 0)
    success_rate = stats.get('success_rate', 0.0) * 100  # Convert to percentage
    chance_of_ruin = stats.get('chance_of_ruin', 0.0) * 100
    num_years = params.get('num_years', 30)
    
    # Calculate return on investment
    if total_withdrawn > 0:
        # Withdrawal strategy: total value = final net worth + withdrawn
        total_value = median_final_net_worth + total_withdrawn
        roi = ((total_value - initial_investment) / initial_investment) * 100 if initial_investment > 0 else 0
        annualized_roi = ((total_value / initial_investment) ** (1 / num_years) - 1) * 100 if initial_investment > 0 else 0
    elif total_contributed > 0:
        # Contribution strategy: ROI based on total invested
        total_invested = initial_investment + total_contributed
        roi = ((median_final_net_worth - total_invested) / total_invested) * 100 if total_invested > 0 else 0
        annualized_roi = ((median_final_net_worth / total_invested) ** (1 / num_years) - 1) * 100 if total_invested > 0 else 0
    else:
        # Simple accumulation
        roi = ((median_final_net_worth - initial_investment) / initial_investment) * 100 if initial_investment > 0 else 0
        annualized_roi = ((median_final_net_worth / initial_investment) ** (1 / num_years) - 1) * 100 if initial_investment > 0 else 0
    
    # Calculate portfolio health score (0-100 composite metric)
    # Factors: success rate (40%), ROI relative to market benchmark (30%), 
    # low chance of ruin (30%)
    roi_score = min(100, max(0, (annualized_roi / 10) * 100))  # 10% annual = 100 score
    ruin_score = 100 - chance_of_ruin
    health_score = (success_rate * 0.4) + (roi_score * 0.3) + (ruin_score * 0.3)
    
    # Prepare data for bubble chart
    # We'll show a single bubble representing this simulation
    strategy_name = params.get('strategy', '').replace('_', ' ').title()
    if params.get('strategy') == 'custom':
        strategy_name = params.get('custom_strategy_name', 'Custom Strategy')
    
    # Data point
    x_values = [annualized_roi]
    y_values = [success_rate]
    sizes = [median_final_net_worth]
    colors = [health_score]
    
    # Hover text with detailed info
    hover_text = (
        f"<b>{strategy_name}</b><br>"
        f"<br>"
        f"<b>Return:</b> {annualized_roi:.1f}% annualized<br>"
        f"<b>Success Rate:</b> {success_rate:.1f}%<br>"
        f"<b>Risk of Ruin:</b> {chance_of_ruin:.1f}%<br>"
        f"<b>Final Value:</b> {format_currency_amount(int(median_final_net_worth), currency, decimals=0)}<br>"
        f"<b>Health Score:</b> {health_score:.0f}/100"
    )
    
    # Create bubble chart
    fig = go.Figure()
    
    # Add the main bubble
    fig.add_trace(go.Scatter(
        x=x_values,
        y=y_values,
        mode='markers',
        marker=dict(
            size=[np.log10(max(1, s)) * 30 for s in sizes],  # Log scale for better visualization
            color=colors,
            colorscale=ExecutiveColors.HEALTH_GRADIENT,
            showscale=True,
            colorbar=dict(
                title="Health<br>Score",
                tickmode="linear",
                tick0=0,
                dtick=25,
                thickness=15,
                len=0.7,
                x=1.02
            ),
            line=dict(
                color='rgba(255, 255, 255, 0.8)',
                width=3
            ),
            opacity=0.85,
            cmin=0,
            cmax=100
        ),
        text=[hover_text],
        hovertemplate='%{text}<extra></extra>',
        name=strategy_name
    ))
    
    # Add reference zones for context
    # Success zone (high success, positive returns)
    fig.add_shape(
        type="rect",
        x0=0, x1=20, y0=80, y1=100,
        fillcolor="rgba(16, 185, 129, 0.1)",
        line=dict(width=0),
        layer="below"
    )
    
    # Add subtle grid for better readability
    fig.update_xaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor='rgba(200, 200, 200, 0.2)',
        zeroline=True,
        zerolinewidth=2,
        zerolinecolor='rgba(150, 150, 150, 0.3)'
    )
    
    fig.update_yaxes(
        showgrid=True,
        gridwidth=1,
        gridcolor='rgba(200, 200, 200, 0.2)'
    )
    
    # Layout with premium styling
    fig.update_layout(
        title=dict(
            text="<b>Financial Health Overview</b>",
            font=dict(size=20, color='#1F2937'),
            x=0.5,
            xanchor='center'
        ),
        xaxis=dict(
            title=dict(
                text="<b>Annualized Return (%)</b>",
                font=dict(size=14, color='#4B5563')
            ),
            tickfont=dict(size=12, color='#6B7280'),
            range=[-5, max(20, annualized_roi * 1.2)]
        ),
        yaxis=dict(
            title=dict(
                text="<b>Success Rate (%)</b>",
                font=dict(size=14, color='#4B5563')
            ),
            tickfont=dict(size=12, color='#6B7280'),
            range=[0, 105]
        ),
        plot_bgcolor=ExecutiveColors.PLOT_BG,  # Light gray with transparency
        paper_bgcolor=ExecutiveColors.PAPER_BG,
        hovermode='closest',
        height=500,
        margin=dict(l=60, r=120, t=80, b=80),
        font=dict(color='#374151'),
        annotations=[
            dict(
                text="<i>Bubble size represents final portfolio value</i>",
                xref="paper", yref="paper",
                x=0.5, y=-0.18,
                showarrow=False,
                font=dict(size=11, color='#9CA3AF'),
                xanchor='center'
            )
        ]
    )
    
    return fig


def create_success_gauges(stats: Dict[str, Any]) -> go.Figure:
    """
    Creates a dashboard of gauge charts showing key success metrics.
    
    Args:
        stats: Final statistics dictionary
        
    Returns:
        Plotly Figure object with gauge charts
    """
    success_rate = stats.get('success_rate', 0.0) * 100
    real_profit_chance = stats.get('chance_of_real_profit', 0.0) * 100
    
    # Calculate composite health score
    chance_of_ruin = stats.get('chance_of_ruin', 0.0) * 100
    health_score = (success_rate + real_profit_chance + (100 - chance_of_ruin)) / 3
    
    # Create subplot with 3 gauges
    fig = go.Figure()
    
    # Define gauge specifications
    gauges = [
        {
            'value': success_rate,
            'title': 'Success Rate',
            'domain': {'x': [0, 0.32], 'y': [0, 1]}
        },
        {
            'value': real_profit_chance,
            'title': 'Real Profit Chance',
            'domain': {'x': [0.34, 0.66], 'y': [0, 1]}
        },
        {
            'value': health_score,
            'title': 'Overall Health',
            'domain': {'x': [0.68, 1], 'y': [0, 1]}
        }
    ]
    
    for gauge in gauges:
        fig.add_trace(go.Indicator(
            mode="gauge+number+delta",
            value=gauge['value'],
            domain=gauge['domain'],
            title={'text': f"<b>{gauge['title']}</b>", 'font': {'size': 16}},
            delta={'reference': 80, 'increasing': {'color': "#10B981"}},
            gauge={
                'axis': {'range': [None, 100], 'tickwidth': 1, 'tickcolor': ExecutiveColors.GAUGE_TICK},
                'bar': {'color': ExecutiveColors.GAUGE_BAR, 'thickness': 0.75},
                'bgcolor': ExecutiveColors.PAPER_BG,
                'borderwidth': 2,
                'bordercolor': ExecutiveColors.GAUGE_BORDER,
                'steps': [
                    {'range': [0, 50], 'color': ExecutiveColors.GAUGE_ZONE_RED},
                    {'range': [50, 75], 'color': ExecutiveColors.GAUGE_ZONE_YELLOW},
                    {'range': [75, 100], 'color': ExecutiveColors.GAUGE_ZONE_GREEN}
                ],
                'threshold': {
                    'line': {'color': "#EF4444", 'width': 4},
                    'thickness': 0.75,
                    'value': 90
                }
            },
            number={'suffix': "%", 'font': {'size': 24, 'color': '#1F2937'}}
        ))
    
    fig.update_layout(
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor='white',
        font=dict(family='Arial, sans-serif', color='#374151')
    )
    
    return fig


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
