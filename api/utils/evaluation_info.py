"""
Strategy evaluation information helper.

Centralized source of truth for "How Evaluation Works" content.
Used in both UI (leaderboard) and PDF/report generation.
"""

from core.strategy_evaluation import HYBRID_PROBING_PARAMS, TEST_SCENARIOS, METRIC_REGISTRY


def get_evaluation_settings_markdown():
    """
    Returns markdown for evaluation simulation settings.
    
    This is the MASTER source of truth - UI and reports both reference this.
    """
    return f"""**Simulation Settings:**
- **Duration**: 30 Years (Withdrawal/Contribution) / 40 Years (Hybrid)
- **Capital**: $1,000,000 (Withdrawal), $100,000 (Contribution)
- **Hybrid Balancing**: Initial capital is dynamically probed per scenario to find a balanced starting point
  - Target: Strategy switches from accumulation to decumulation at {int(HYBRID_PROBING_PARAMS['target_transition_ratio']*100)}% of the simulation duration
  - Tolerance: ±{int(HYBRID_PROBING_PARAMS['tolerance']*100)}%
- **Environment**: 2% Inflation, 1% Wealth Tax (ISK)
- **Execution**: 1000 Monte Carlo simulations per scenario
- **Configuration**: Strategies are evaluated using their default parameters"""


def get_market_scenarios_markdown():
    """
    Returns markdown for market scenarios description.
    
    This is the MASTER source of truth - dynamically generated from TEST_SCENARIOS.
    """
    lines = []
    for i, s in enumerate(TEST_SCENARIOS, 1):
        lines.append(
            f"{i}. **{s['name']}** ({int(s['annual_return']*100)}% return, "
            f"{int(s['annual_volatility']*100)}% volatility) - {int(s['weight']*100)}% weight"
        )
    
    scenarios_text = '\n'.join(lines)
    
    # Calculate stress scenario weight
    stress_weight = int(sum(s['weight'] for s in TEST_SCENARIOS if 'Bear' in s['name']) * 100)
    
    return f"""{scenarios_text}

**Note**: Stress scenarios (Bear, Extreme Bear) account for {stress_weight}% of the total weight."""


def get_score_components_markdown(category=None):
    """
    Returns markdown for score components description, filtered by category.
    
    This is the MASTER source of truth - dynamically generated from METRIC_REGISTRY.
    
    Args:
        category: Optional strategy category ('CONTRIBUTION_ONLY', 'WITHDRAWAL_ONLY', 'HYBRID', None)
                 If provided, only shows metrics applicable to that category.
    """
    lines = []
    excluded = {'adequacy_score', 'usability_score'}
    
    for key, metric in METRIC_REGISTRY.items():
        if key not in excluded:
            # Filter by category if specified
            if category is not None and hasattr(metric, 'is_applicable'):
                if not metric.is_applicable(category):
                    continue  # Skip non-applicable metrics
            
            description = metric.describe_score_components()
            if description:  # Only include non-empty descriptions
                lines.append(description)
    
    metrics_text = '\n'.join(lines)
    
    category_note = ""
    if category:
        category_labels = {
            'CONTRIBUTION_ONLY': 'Accumulation Strategies',
            'WITHDRAWAL_ONLY': 'Withdrawal Strategies',
            'HYBRID': 'Lifecycle Strategies'
        }
        label = category_labels.get(category, 'All Strategies')
        category_note = f"\n\n*Showing metrics applicable to {label}*\n"
    
    return f"""**Excellence Score (0-100)** = Weighted combination of the following metrics:

{metrics_text}{category_note}"""



def get_wisdom_of_crowd_markdown():
    """
    Returns markdown for Wisdom of the Crowd section.
    
    This is the MASTER source of truth.
    """
    return """The leaderboard is a **collective intelligence engine**. Research shows that diverse groups often outperform individual experts when:
- There's a **clear scoring mechanism** (Excellence Score)
- Contributors are **independent** (users from different backgrounds)
- Results are **aggregated effectively** (the leaderboard)

As thousands of users create and refine strategies, the top performers represent the **collective wisdom** of the community—potentially discovering approaches that no single financial advisor would design alone.

📚 *Based on ["The Wisdom of Crowds" (Surowiecki, 2004)](https://en.wikipedia.org/wiki/The_Wisdom_of_Crowds)*"""


def get_evaluation_works_full_markdown():
    """
    Returns complete "How Evaluation Works" content as markdown.
    
    Used in reports/PDFs. UI uses individual sections for more control.
    """
    return f"""### Evaluation Process

Strategies on the leaderboard are stress-tested across **8 standardized market scenarios** to evaluate robustness and performance.

{get_evaluation_settings_markdown()}

### Market Scenarios

{get_market_scenarios_markdown()}

### Score Components

{get_score_components_markdown()}

### 🧠 Wisdom of the Crowd

{get_wisdom_of_crowd_markdown()}"""
