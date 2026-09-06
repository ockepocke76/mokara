"""
Simulation methodology flowchart generation.
Provides the flowchart as Mermaid diagram code for use in UI and PDF.
"""

import os
import logging

def get_simulation_flowchart_mermaid():
    """
    Returns the simulation process flowchart as Mermaid diagram code.
    Can be rendered in Streamlit UI and converted to image for PDF.
    """
    return """
graph TD
    A[Simulation Settings] --> B[Data Preparation]
    B --> C[Monte Carlo Engine]
    C --> D{Generate N Scenarios}
    D --> E[Strategy Logic]
    D --> F[Portfolio Bookkeeping]
    D --> G[Market Simulation]
    E --> H[Statistical Analysis]
    F --> H
    G --> H
    H --> I[Results & Visualization]
    
    style A fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff
    style B fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff
    style C fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff
    style D fill:#7B68EE,stroke:#5346B8,stroke-width:2px,color:#fff
    style E fill:#50C878,stroke:#3A9B5C,stroke-width:2px,color:#fff
    style F fill:#50C878,stroke:#3A9B5C,stroke-width:2px,color:#fff
    style G fill:#50C878,stroke:#3A9B5C,stroke-width:2px,color:#fff
    style H fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff
    style I fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff
    
    classDef default fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff
"""

def get_simulation_flowchart_detailed_mermaid():
    """
    Returns a detailed, accurate simulation flowchart based on the actual codebase implementation.
    Shows iterative loops, AI analysis, and the complete simulation pipeline.
    Layout is vertical (TD) for better fit in 3:2 aspect ratio.
    """
    return """
graph TD
    Start([User Input]) --> Settings["⚙️ Simulation Settings<br/><small>Portfolio parameters<br/>Strategy selection<br/>Time horizon</small>"]
    Settings --> DataPrep["📈 Data Preparation<br/><small>Load historical prices<br/>Calculate returns distribution<br/>Risk parameters</small>"]
    DataPrep --> Scenarios["🎲 Generate Return Scenarios<br/><small>Historical backtest<br/>Monte Carlo scenarios<br/>(bootstrap or parametric)</small>"]
    
    Scenarios --> MainLoop{For Each<br/>Scenario}
    
    MainLoop -->|N scenarios| InitPort["🏦 Initialize Portfolio<br/><small>Set initial capital<br/>Execute initial strategy<br/>Record Year 0 state</small>"]
    
    InitPort --> YearLoop{For Each<br/>Year}
    
    YearLoop -->|1 to N years| MarketEvent["📉 Market Event<br/><small>Apply annual return<br/>Update asset value</small>"]
    
    MarketEvent --> CashInterest["💰 Accrue Interest<br/><small>Interest on cash<br/>Interest on debt</small>"]
    
    CashInterest --> StrategyExec["🎯 Strategy Execution<br/><small>Calculate drawdown needs<br/>Evaluate portfolio state<br/>Make decisions</small>"]
    
    StrategyExec --> PortfolioMgmt["📒 Portfolio Management<br/><small>Execute transactions<br/>Asset sales/purchases<br/>Loan drawdown/repayment<br/>Tax calculations</small>"]
    
    PortfolioMgmt --> RecordState["💾 Record State<br/><small>Snapshot yearly results<br/>Track all metrics</small>"]
    
    RecordState --> YearLoop
    
    YearLoop -->|Complete| StoreResult["📦 Store Scenario Result<br/><small>Save path data<br/>Final outcomes</small>"]
    
    StoreResult --> MainLoop
    
    MainLoop -->|All scenarios<br/>complete| Statistics["📊 Statistical Analysis<br/><small>Calculate percentiles<br/>Risk metrics<br/>Outcome probabilities</small>"]
    
    Statistics --> Visualize["📈 Generate Visualizations<br/><small>Interactive plots<br/>Distribution charts<br/>Time series</small>"]
    
    Visualize --> AI["🤖 AI Analysis<br/><small>Qualitative insights<br/>Risk assessment<br/>Recommendations</small>"]
    
    AI --> PDFGen["📄 PDF Generation<br/><small>Compile report<br/>Charts & tables<br/>Executive summary</small>"]
    
    PDFGen --> End([Results Delivered])
    
    style Start fill:#7B68EE,stroke:#5346B8,stroke-width:3px,color:#fff
    style Settings fill:#4A90E2,stroke:#2E5C8A,stroke-width:3px,color:#fff
    style DataPrep fill:#4A90E2,stroke:#2E5C8A,stroke-width:3px,color:#fff
    style Scenarios fill:#4A90E2,stroke:#2E5C8A,stroke-width:3px,color:#fff
    style MainLoop fill:#FF6B6B,stroke:#C92A2A,stroke-width:3px,color:#fff
    style InitPort fill:#50C878,stroke:#3A9B5C,stroke-width:2px,color:#fff
    style YearLoop fill:#FF6B6B,stroke:#C92A2A,stroke-width:3px,color:#fff
    style MarketEvent fill:#FFA500,stroke:#CC8400,stroke-width:2px,color:#fff
    style CashInterest fill:#FFA500,stroke:#CC8400,stroke-width:2px,color:#fff
    style StrategyExec fill:#50C878,stroke:#3A9B5C,stroke-width:2px,color:#fff
    style PortfolioMgmt fill:#50C878,stroke:#3A9B5C,stroke-width:2px,color:#fff
    style RecordState fill:#50C878,stroke:#3A9B5C,stroke-width:2px,color:#fff
    style StoreResult fill:#4A90E2,stroke:#2E5C8A,stroke-width:2px,color:#fff
    style Statistics fill:#4A90E2,stroke:#2E5C8A,stroke-width:3px,color:#fff
    style Visualize fill:#4A90E2,stroke:#2E5C8A,stroke-width:3px,color:#fff
    style AI fill:#9B59B6,stroke:#6C3483,stroke-width:3px,color:#fff
    style PDFGen fill:#4A90E2,stroke:#2E5C8A,stroke-width:3px,color:#fff
    style End fill:#7B68EE,stroke:#5346B8,stroke-width:3px,color:#fff
"""

def _try_generate_with_python(mermaid_code, output_path, bg_color):
    """
    Try to generate PNG using Python-based methods (Playwright or API).
    
    Args:
        mermaid_code: The Mermaid diagram code
        output_path: Where to save the PNG
        bg_color: Background color (hex like '#0a192f' or '#ffffff')
    """
    try:
        from reporting.generate_flowchart import generate_flowchart_png
        return generate_flowchart_png(mermaid_code, output_path, bg_color)
    except Exception as e:
        logging.debug(f"Python-based generation failed: {e}")
        return False

def _try_generate_with_mermaid_cli(mermaid_code, output_path, bg_color=None):
    """
    Try to generate PNG using mermaid-cli (mmdc).
    
    Args:
        mermaid_code: The Mermaid diagram code
        output_path: Where to save the PNG
        bg_color: Background color (hex like '#0a192f' for dark, '#ffffff' for white, or 'transparent')
    """
    import subprocess
    import tempfile
    
    try:
        # Create temporary mermaid file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mmd', delete=False) as f:
            f.write(mermaid_code)
            mmd_path = f.name
        
        # Build mmdc command
        cmd = ['mmdc', '-i', mmd_path, '-o', output_path]
        
        # Add background color if specified
        if bg_color:
            cmd.extend(['-b', bg_color])
        
        # Try to run mmdc
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=10
        )
        
        # Clean up temp file
        os.unlink(mmd_path)
        
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logging.debug(f"mermaid-cli not available: {e}")
        return False

def ensure_flowchart_image(output_dir="assets", bg="dark"):
    """
    Ensures the flowchart PNG exists.
    If it exists, uses it directly. If not, generates it.
    
    Args:
        output_dir: Directory to store the flowchart
        bg: Background style - "dark" for UI (dark background) or "white" for PDF (white background)
    
    Returns:
        str: Path to the flowchart PNG file, or None if generation failed
    """
    import time
    start_time = time.time()
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Use different files for dark and light backgrounds
    suffix = "_dark" if bg == "dark" else "_light"
    png_path = os.path.join(output_dir, f"simulation_flowchart{suffix}.png")
    
    # Simple check: if PNG exists, use it
    if os.path.exists(png_path):
        check_time = time.time() - start_time
        logging.info(f"✅ FLOWCHART: Using existing ({bg}) flowchart - checked in {check_time:.3f}s")
        return png_path
    
    # PNG doesn't exist, need to generate
    logging.info(f"Flowchart PNG ({bg}) missing, generating...")
    gen_start = time.time()
    
    # Get Mermaid code
    mermaid_code = get_simulation_flowchart_detailed_mermaid()
    
    # Determine background color based on bg parameter
    bg_color = '#0a192f' if bg == 'dark' else '#ffffff'
    
    # Try mermaid-cli first (fastest if available)
    if _try_generate_with_mermaid_cli(mermaid_code, png_path, bg_color):
        gen_time = time.time() - gen_start
        logging.info(f"✅ FLOWCHART: Generated using mermaid-cli ({bg}) in {gen_time:.3f}s")
        return png_path
    
    # Try Python-based generation (Playwright or API)
    logging.info("mermaid-cli not available, trying Python-based generation...")
    if _try_generate_with_python(mermaid_code, png_path, bg_color):
        gen_time = time.time() - gen_start
        logging.info(f"✅ FLOWCHART: Generated using Python ({bg}) in {gen_time:.3f}s")
        return png_path
    
    # All generation methods failed
    logging.warning(
        "Could not generate flowchart PNG.\n"
        "Install one of: \n"
        "  1. npm install -g @mermaid-js/mermaid-cli\n"
        "  2. pip install playwright && playwright install chromium\n"
        "  3. pip install requests (for API fallback)\n"
    )
    return None

