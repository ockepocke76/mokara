"""
Centralized color scheme for all plots and UI elements.
Provides consistent theming across the application.
"""

# Module-level cache for theme (avoid repeated YAMLparsing - ~8s overhead!)
_cached_theme = None


# ============================================================================
# DARK THEME COLORS (for Plotly interactive charts)
# ============================================================================

class DarkTheme:
    """Colors for the dark theme used in Plotly interactive charts."""
    
    # Background colors
    PAPER_BG = '#0a192f'
    PLOT_BG = '#0a192f'
    
    # Grid and lines
    GRID_COLOR = '#172a45'
    LINE_COLOR = '#303C55'
    ZEROLINE_COLOR = '#172a45'
    
    # Fonts
    FONT_COLOR = '#ccd6f6'
    TITLE_FONT_COLOR = '#EAEAEA'
    
    # UI elements
    LEGEND_BG = 'rgba(0,0,0,0)'  # Transparent
    UPDATEMENU_BG = '#303C55'
    UPDATEMENU_BORDER = '#64ffda'


# ============================================================================
# LIGHT THEME COLORS (for Plotly interactive charts)
# ============================================================================

class LightTheme:
    """Colors for the light/bright theme used in Plotly interactive charts."""
    
    # Background colors
    PAPER_BG = 'white'
    PLOT_BG = '#f8f9fa'  # Very light gray
    
    # Grid and lines
    GRID_COLOR = '#dee2e6'  # Light gray
    LINE_COLOR = '#adb5bd'  # Medium gray
    ZEROLINE_COLOR = '#ced4da'  # Light gray
    
    # Fonts
    FONT_COLOR = '#212529'  # Dark gray (almost black)
    TITLE_FONT_COLOR = '#343a40'  # Dark gray
    
    # UI elements
    LEGEND_BG = 'rgba(255,255,255,0.9)'  # Semi-transparent white
    UPDATEMENU_BG = '#e9ecef'  # Light gray
    UPDATEMENU_BORDER = '#495057'  # Dark gray


# ============================================================================
# DATA VISUALIZATION COLORS
# ============================================================================

class ChartColors:
    """Colors for data visualization elements in charts and plots."""
    
    # Primary accent color (used for main data lines, highlights)
    PRIMARY = '#64ffda'  # Teal/cyan
    
    # Statistical line colors
    MEDIAN = '#e74c3c'  # Red
    MEAN = '#f1c40f'  # Yellow
    P25 = '#9b59b6'  # Purple (25th percentile)
    P75 = '#2ecc71'  # Green (75th percentile)
    
    # Data series colors
    SIMULATION_PATH = '#3498db'  # Blue
    INITIAL_INVESTMENT = '#ff6b6b'  # Bright red
    HISTORICAL_BACKTEST = 'white'
    
    # Shaded areas / fills
    IQR_FILL = 'rgba(100, 255, 218, 0.2)'  # Teal with transparency
    IQR_FILL_BORDER = 'rgba(255,255,255,0)'  # Invisible border
    
    # Distribution/histogram colors
    DISTRIBUTION = '#3498db'  # Blue
    DISTRIBUTION_FILL = 'rgba(52, 152, 219, 0.75)'
    
    # Yearly returns (conditional colors)
    POSITIVE_RETURN = '#3498db'  # Blue
    NEGATIVE_RETURN = '#e74c3c'  # Red
    
    # Drawdown colors
    DRAWDOWN_LINE = '#e74c3c'  # Red
    DRAWDOWN_FILL = 'rgba(231, 76, 60, 0.4)'
    
    # Overview chart colors
    NET_WORTH_IQR = 'rgba(0,100,80,0.2)'
    NET_WORTH_MEDIAN = 'rgba(0,100,80,1)'
    ASSET_VALUE_IQR = 'rgba(0,176,246,0.2)'
    ASSET_VALUE_MEDIAN = 'rgba(0,176,246,1)'
    
    # Cash flow colors
    CONTRIBUTIONS = 'blue'
    TOTAL_COSTS = 'purple'
    DEBT = 'red'
    CASH = '#2ecc71'  # Green
    DRAWDOWN = 'orange'
    
    # Autocorrelation colors
    ACF_BAR = '#3498db'  # Blue
    ACF_CONFIDENCE_FILL = 'rgba(100, 255, 218, 0.1)'
    ACF_CONFIDENCE_BORDER = 'rgba(255,255,255,0)'
    
    # Threshold/warning colors
    THRESHOLD_WARNING = '#f39c12'  # Orange


class LightChartColors:
    """Colors for data visualization elements in charts and plots (Light Theme/PDF)."""
    
    # Primary accent color (darker for white background)
    PRIMARY = '#00796b'  # Dark Teal
    
    # Statistical line colors (darker for contrast)
    MEDIAN = '#c0392b'  # Darker Red
    MEAN = '#f39c12'  # Darker Orange/Yellow
    P25 = '#8e44ad'  # Darker Purple
    P75 = '#27ae60'  # Darker Green
    
    # Data series colors
    SIMULATION_PATH = '#2980b9'  # Darker Blue
    INITIAL_INVESTMENT = '#c0392b'  # Darker Red
    HISTORICAL_BACKTEST = '#2c3e50' # Dark Gray/Blue
    
    # Shaded areas / fills (same as dark usually works, but can tweak)
    IQR_FILL = 'rgba(0, 150, 136, 0.2)'  # Teal with transparency
    IQR_FILL_BORDER = 'rgba(255,255,255,0)'  # Invisible border
    
    # Distribution/histogram colors
    DISTRIBUTION = '#2980b9'  # Darker Blue
    DISTRIBUTION_FILL = 'rgba(41, 128, 185, 0.75)'
    
    # Yearly returns (conditional colors)
    POSITIVE_RETURN = '#2980b9'  # Darker Blue
    NEGATIVE_RETURN = '#c0392b'  # Darker Red
    
    # Drawdown colors
    DRAWDOWN_LINE = '#c0392b'  # Darker Red
    DRAWDOWN_FILL = 'rgba(192, 57, 43, 0.4)'
    
    # Overview chart colors
    NET_WORTH_IQR = 'rgba(22, 160, 133, 0.2)'
    NET_WORTH_MEDIAN = 'rgba(22, 160, 133, 1)' # Darker Teal
    ASSET_VALUE_IQR = 'rgba(41, 128, 185, 0.2)'
    ASSET_VALUE_MEDIAN = 'rgba(41, 128, 185, 1)' # Darker Blue
    
    # Cash flow colors
    CONTRIBUTIONS = '#0d47a1' # Very Dark Blue
    TOTAL_COSTS = '#4a148c' # Very Dark Purple
    DEBT = '#b71c1c' # Very Dark Red
    CASH = '#1b5e20'  # Very Dark Green
    DRAWDOWN = '#e65100' # Dark Orange
    
    # Autocorrelation colors
    ACF_BAR = '#2980b9'  # Darker Blue
    ACF_CONFIDENCE_FILL = 'rgba(0, 150, 136, 0.1)'
    ACF_CONFIDENCE_BORDER = 'rgba(255,255,255,0)'
    
    # Threshold/warning colors
    THRESHOLD_WARNING = '#d35400'  # Pumpkin/Dark Orange


def get_chart_colors(theme_name='dark'):
    """
    Returns the appropriate ChartColors class based on the theme.
    """
    if theme_name == 'light':
        return LightChartColors
    return ChartColors


# ============================================================================
# FLOWCHART COLORS (for Mermaid diagrams)
# ============================================================================

class FlowchartColors:
    """Colors for flowchart nodes and elements (dark theme)."""
    
    # Node background colors
    START_END = '#7B68EE'  # Purple
    START_END_STROKE = '#5346B8'
    
    CALCULATE = '#4A90E2'  # Blue
    CALCULATE_STROKE = '#2E5C8A'
    
    ACTION = '#FFA500'  # Orange
    ACTION_STROKE = '#CC8400'
    
    ENGINE_PROCESS = '#50C878'  # Emerald
    ENGINE_PROCESS_STROKE = '#3A9B5C'
    
    DECISION_CHECK = '#FF6B6B'  # Red
    DECISION_CHECK_STROKE = '#C92A2A'
    
    # Flowchart background
    BACKGROUND = '#0a192f'  # Dark blue (matches dark theme)
    
    # Line/edge color for flowcharts
    LINE_COLOR = '#4C78A8'
    FILL_COLOR = 'rgba(76, 120, 168, 0.3)'


class LightFlowchartColors:
    """Colors for flowchart nodes and elements (light theme)."""
    
    # Node background colors - slightly darker for visibility on white
    START_END = '#6658D3'  # Darker purple
    START_END_STROKE = '#4838A0'
    
    CALCULATE = '#357ABD'  # Darker blue
    CALCULATE_STROKE = '#245A8D'
    
    ACTION = '#E69500'  # Darker orange
    ACTION_STROKE = '#B87500'
    
    ENGINE_PROCESS = '#45B369'  # Darker emerald
    ENGINE_PROCESS_STROKE = '#308A4D'
    
    DECISION_CHECK = '#E85555'  # Darker red
    DECISION_CHECK_STROKE = '#B82020'
    
    # Flowchart background
    BACKGROUND = '#FFFFFF'  # White
    
    # Line/edge color for flowcharts
    LINE_COLOR = '#3B6A96'
    FILL_COLOR = 'rgba(59, 106, 150, 0.2)'


# ============================================================================
# EXECUTIVE DASHBOARD COLORS
# ============================================================================

class ExecutiveColors:
    """Colors for executive summary visualizations."""
    
    # Health score gradient (poor to excellent)
    HEALTH_GRADIENT = [
        [0, '#EF4444'],      # Red (poor health)
        [0.25, '#F59E0B'],   # Amber (moderate)
        [0.5, '#FCD34D'],    # Yellow
        [0.75, '#84CC16'],   # Lime
        [1, '#10B981']       # Emerald (excellent health)
    ]
    
    # Gauge chart colors
    GAUGE_BAR = '#6366F1'  # Indigo
    GAUGE_BORDER = '#E5E7EB'  # Light gray
    GAUGE_TICK = '#6B7280'  # Gray
    
    # Gauge zones (background steps)
    GAUGE_ZONE_RED = '#FEE2E2'
    GAUGE_ZONE_YELLOW = '#FEF3C7'
    GAUGE_ZONE_GREEN = '#D1FAE5'
    
    # Traffic light verdict colors
    VERDICT_GREEN = '#059669'  # Emerald (low risk)
    VERDICT_YELLOW = '#D97706'  # Amber (moderate risk)
    VERDICT_RED = '#DC2626'  # Red (high risk)
    
    # Bubble chart
    BUBBLE_BORDER = 'rgba(255, 255, 255, 0.8)'
    SUCCESS_ZONE_FILL = 'rgba(16, 185, 129, 0.1)'
    
    # Text colors
    TITLE_COLOR = '#1F2937'  # Dark gray
    SUBTITLE_COLOR = '#4B5563'  # Medium gray
    CAPTION_COLOR = '#9CA3AF'  # Light gray
    LABEL_COLOR = '#6B7280'  # Gray
    
    # Background colors
    PLOT_BG = 'rgba(249, 250, 251, 0.5)'  # Light gray with transparency
    PAPER_BG = 'white'


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_flowchart_style(node_type, theme='dark'):
    """
    Get the Mermaid style string for a flowchart node type.
    
    Args:
        node_type: Type of node ('start_end', 'calculate', 'action', 'engine', 'decision')
        theme: Theme name ('dark' or 'light')
    
    Returns:
        String with fill and stroke colors for Mermaid diagram
    """
    # Select the appropriate color scheme
    Colors = LightFlowchartColors if theme == 'light' else FlowchartColors
    
    styles = {
        'start_end': f'fill:{Colors.START_END},stroke:{Colors.START_END_STROKE},stroke-width:3px,color:#fff',
        'calculate': f'fill:{Colors.CALCULATE},stroke:{Colors.CALCULATE_STROKE},stroke-width:3px,color:#fff',
        'action': f'fill:{Colors.ACTION},stroke:{Colors.ACTION_STROKE},stroke-width:3px,color:#fff',
        'engine': f'fill:{Colors.ENGINE_PROCESS},stroke:{Colors.ENGINE_PROCESS_STROKE},stroke-width:3px,color:#fff',
        'decision': f'fill:{Colors.DECISION_CHECK},stroke:{Colors.DECISION_CHECK_STROKE},stroke-width:3px,color:#fff',
    }
    return styles.get(node_type, '')


def get_theme(theme_name='dark'):
    """
    Get the appropriate theme class based on the theme name.
    
    Args:
        theme_name: Name of theme ('dark' or 'light')
    
    Returns:
        Theme class (DarkTheme or LightTheme)
    """
    if theme_name.lower() == 'light':
        return LightTheme
    return DarkTheme


def get_chart_theme():
    """
    Get the current chart theme name from config.yml.
    
    Returns:
        'light' or 'dark' (defaults to 'dark' if config cannot be read)
    """
    global _cached_theme
    
    # Return cached value if available
    if _cached_theme is not None:
        return _cached_theme
    
    try:
        import yaml
        import os
        
        config_path = os.path.join(os.path.dirname(__file__), '..', 'config.yml')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                _cached_theme = config.get('ui', {}).get('chart_theme', {}).get('value', 'dark')
                return _cached_theme
    except Exception:
        pass
    
    _cached_theme = 'dark'
    return _cached_theme


def get_plotly_theme_template(theme_name='dark'):
    """
    Returns a dictionary with Plotly template configuration for the specified theme.
    
    Args:
        theme_name: Name of theme ('dark' or 'light')
    
    Returns:
        Dictionary with Plotly template configuration
    """
    Theme = get_theme(theme_name)
    
    return {
        'layout': {
            'font_color': Theme.FONT_COLOR,
            'paper_bgcolor': Theme.PAPER_BG,
            'plot_bgcolor': Theme.PLOT_BG,
            'xaxis': {
                'gridcolor': Theme.GRID_COLOR,
                'linecolor': Theme.LINE_COLOR,
                'zerolinecolor': Theme.ZEROLINE_COLOR
            },
            'yaxis': {
                'gridcolor': Theme.GRID_COLOR,
                'linecolor': Theme.LINE_COLOR,
                'zerolinecolor': Theme.ZEROLINE_COLOR
            },
            'legend': {
                'bgcolor': Theme.LEGEND_BG
            },
            'title_font_color': Theme.TITLE_FONT_COLOR,
            'updatemenudefaults': {
                'font': {'color': Theme.FONT_COLOR},
                'bgcolor': Theme.UPDATEMENU_BG,
                'active': 0,
                'bordercolor': Theme.UPDATEMENU_BORDER
            }
        }
    }
