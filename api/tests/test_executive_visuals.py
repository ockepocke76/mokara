"""The one executive visual in production use: the verdict traffic light
(embedded in reports by background_tasks). The bubble/gauge builders were
deleted in R4 — this replaces the old manual print-script that exercised
them."""
import plotly.graph_objects as go

from reporting.executive_visuals import create_verdict_traffic_light

SAMPLE_STATS = {
    'success_rate': 0.92,
    'chance_of_ruin': 0.05,
    'chance_of_real_profit': 0.95,
    'median_final_net_worth': 3_500_000,
}


def test_traffic_light_builds_a_figure():
    fig = create_verdict_traffic_light(SAMPLE_STATS)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) > 0


def test_traffic_light_mobile_variant():
    fig = create_verdict_traffic_light(SAMPLE_STATS, mobile=True)
    assert isinstance(fig, go.Figure)
