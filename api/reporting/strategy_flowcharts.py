"""
Strategy-specific decision flowcharts.
Shows how each strategy makes annual decisions during simulation.
"""

from reporting.color_scheme import get_flowchart_style

def get_trinity_strategy_flowchart(theme='dark'):
    """
    Flowchart showing Trinity Study (4% Rule) decision logic.
    Using LR layout with compact nodes for better square fit.
    
    Args:
        theme: 'dark' or 'light' theme for colors
    """
    return """
flowchart LR
    Start(["🎯 START<br/>YEAR"]) --> Calc["💰 CALCULATE<br/>WITHDRAWAL<br/><br/>4% of initial<br/>× inflation factor"]
    Calc --> Sell["📉 REQUEST<br/>ASSET SALE<br/><br/>Amount = withdrawal<br/>+ known costs"]
    Sell --> Engine["⚙️ ENGINE<br/>PROCESSING<br/><br/>• Execute sale<br/>• Calculate taxes<br/>• Update portfolio"]
    Engine --> Done(["✅ YEAR<br/>COMPLETE"])
    
    style Start {style_start}
    style Calc {style_calc}
    style Sell {style_action}
    style Engine {style_engine}
    style Done {style_start}
""".format(
    style_start=get_flowchart_style('start_end', theme=theme),
    style_calc=get_flowchart_style('calculate', theme=theme),
    style_action=get_flowchart_style('action', theme=theme),
    style_engine=get_flowchart_style('engine', theme=theme)
)

def get_bbd_strategy_flowchart(theme='dark'):
    """
    Flowchart showing Buy, Borrow, Die strategy decision logic.
    Using tall nodes for square format.
    
    Args:
        theme: 'dark' or 'light' theme for colors
    """
    return """
graph TD
    Start([🎯 START YEAR]) --> CheckCash["💵 CHECK CASH NEEDS<br/><br/>Calculate annual drawdown<br/>(4% of initial, inflation-adjusted)<br/>Do we need cash this year?"]
    
    CheckCash --> CheckLTV["📊 CHECK LOAN-TO-VALUE<br/><br/>Current LTV = Debt ÷ Assets<br/>Can we borrow more?<br/>(LTV must be less than 50%)"]
    
    CheckLTV --> Borrow["💳 BORROW MONEY<br/><br/>Take tax-free loan against assets<br/>No capital gains taxes!<br/>Increases debt but preserves assets"]
    
    Borrow --> Done([✅ YEAR COMPLETE])
    
    CheckLTV -."LTV ≥ 50%<br/>(Can't borrow)".-> Sell["📉 SELL ASSETS<br/><br/>Liquidate portfolio<br/>Pay capital gains taxes<br/>Last resort when leverage limit hit"]
    
    Sell --> Done
    
    style Start {style_start}
    style CheckCash {style_calc}
    style CheckLTV {style_decision}
    style Borrow {style_engine}
    style Sell {style_action}
    style Done {style_start}
""".format(
    style_start=get_flowchart_style('start_end', theme=theme) + ',font-size:14px',
    style_calc=get_flowchart_style('calculate', theme=theme) + ',font-size:13px',
    style_decision=get_flowchart_style('decision', theme=theme) + ',font-size:13px',
    style_engine=get_flowchart_style('engine', theme=theme) + ',font-size:13px',
    style_action=get_flowchart_style('action', theme=theme) + ',font-size:13px'
)

def get_grsr_strategy_flowchart(theme='dark'):
    """
    Flowchart showing Get Rich Stay Rich strategy decision logic.
    Using tall nodes for square format.
    
    Args:
        theme: 'dark' or 'light' theme for colors
    """
    return """
graph TD
    Start([🎯 START YEAR]) --> CheckPhase["📊 CHECK WEALTH PHASE<br/><br/>Is portfolio value above target?<br/>Target = Desired wealth goal<br/>Determines allocation strategy"]
    
    CheckPhase --> GrowthMode["🚀 GROWTH MODE<br/><br/>Below target - Go aggressive!<br/>100% stocks allocation<br/>Maximize returns to reach goal"]
    
    CheckPhase -."Above target".-> PreserveMode["🛡️ PRESERVATION MODE<br/><br/>Above target - Protect wealth!<br/>Rebalance to bonds & cash<br/>Reduce volatility risk"]
    
    GrowthMode --> Withdraw1["💰 HANDLE WITHDRAWALS<br/><br/>Sell stocks if cash needed<br/>Pay capital gains taxes<br/>Stay invested otherwise"]
    
    PreserveMode --> Withdraw2["💰 HANDLE WITHDRAWALS<br/><br/>Sell bonds/cash first (safer)<br/>Only touch stocks if needed<br/>Pay applicable taxes"]
    
    Withdraw1 --> Done([✅ YEAR COMPLETE])
    Withdraw2 --> Done
    
    style Start {style_start}
    style CheckPhase {style_decision}
    style GrowthMode {style_engine}
    style PreserveMode {style_calc}
    style Withdraw1 {style_action}
    style Withdraw2 {style_action}
    style Done {style_start}
""".format(
    style_start=get_flowchart_style('start_end', theme=theme) + ',font-size:14px',
    style_decision=get_flowchart_style('decision', theme=theme) + ',font-size:13px',
    style_engine=get_flowchart_style('engine', theme=theme) + ',font-size:13px',
    style_calc=get_flowchart_style('calculate', theme=theme) + ',font-size:13px',
    style_action=get_flowchart_style('action', theme=theme) + ',font-size:13px'
)

def get_strategy_flowchart(strategy_name, theme='dark'):
    """
    Get the decision flowchart for a specific strategy.
    
    Args:
        strategy_name: Name of the strategy ("trinity", "bbd", "grsr")
        theme: 'dark' or 'light' theme for colors
    
    Returns:
        str: Mermaid diagram code for the strategy flowchart
    """
    # Guard against None or empty strategy names
    if not strategy_name:
        return """
graph TD
    Error([⚠️ No Strategy Selected])
    style Error fill:#ff6b6b,stroke:#c92a2a,stroke-width:2px,color:#fff
"""
    
    strategy_map = {
        "trinity": get_trinity_strategy_flowchart,
        "bbd": get_bbd_strategy_flowchart,
        "buy borrow die": get_bbd_strategy_flowchart,
        "grsr": get_grsr_strategy_flowchart,
        "get rich stay rich": get_grsr_strategy_flowchart,
    }
    
    flowchart_func = strategy_map.get(strategy_name.lower().strip())
    if flowchart_func:
        return flowchart_func(theme=theme)
    
    # Fallback for unknown strategies
    return """
graph TD
    Start([Strategy Decision]) --> Info["ℹ️ Custom Strategy<br/>Flowchart not available<br/>for custom strategies"]
    Info --> End([Implementation Specific])
    
    style Start {style_start}
    style Info {style_calc}
    style End {style_engine}
""".format(
    style_start=get_flowchart_style('start_end', theme=theme) + ',stroke-width:2px',
    style_calc=get_flowchart_style('calculate', theme=theme) + ',stroke-width:2px',
    style_engine=get_flowchart_style('engine', theme=theme) + ',stroke-width:2px'
)
