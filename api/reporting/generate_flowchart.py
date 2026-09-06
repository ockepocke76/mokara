"""
Python-based flowchart PNG generator using Playwright (headless browser).
This allows generating flowcharts without requiring npm/mermaid-cli.
"""

import os
import logging
from pathlib import Path


def generate_flowchart_with_playwright(mermaid_code: str, output_path: str, bg_color: str = "#ffffff") -> bool:
    """
    Generate flowchart PNG using Playwright (headless Chromium).
    
    Args:
        mermaid_code: Mermaid diagram code
        output_path: Where to save the PNG
        bg_color: Background color (hex like '#0a192f' or '#ffffff')
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        from playwright.sync_api import sync_playwright
        
        # Create HTML with Mermaid
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <script type="module">
        import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs';
        mermaid.initialize({{ 
            startOnLoad: true,
            theme: 'base',
            themeVariables: {{
                background: '{bg_color}',
                primaryColor: '#4A90E2',
                primaryTextColor: '#fff',
                primaryBorderColor: '#2E5C8A',
                lineColor: '#8892b0',
                secondaryColor: '#50C878',
                tertiaryColor: '#FFA500'
            }},
            flowchart: {{
                useMaxWidth: false,      // Don't compress to fit width
                htmlLabels: true,
                nodeSpacing: 100,        // More horizontal space between nodes  
                rankSpacing: 100,        // More vertical space between levels
                padding: 30,             // Padding around nodes
                wrappingWidth: 200,      // Text wraps at 200px for readability
                curve: 'basis'           // Smoother curves for connectors
            }}
        }});
    </script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        html, body {{
            width: 100%;
            min-height: 100vh;
            background: {bg_color};
            overflow: visible;
            margin: 0;
            padding: 0;
        }}
        .mermaid-container {{
            width: 100%;
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 40px;
        }}
        .mermaid {{
            display: inline-block;
        }}
        /* Make nodes wider to better use horizontal space in TD layout */
        .mermaid svg .node rect {{
            min-width: 250px !important;
            rx: 8px !important;  /* Rounded corners */
            ry: 8px !important;
        }}
        .mermaid svg .node circle {{
            r: 60px !important;  /* Bigger circles for start/end */
        }}
        /* Improve text readability */
        .mermaid svg .nodeLabel {{
            font-size: 14px !important;
            line-height: 1.4 !important;
            padding: 12px !important;
        }}
        /* Style edges/connectors */
        .mermaid svg .edgePath path {{
            stroke-width: 2.5px !important;
        }}
        .mermaid svg .edgeLabel {{
            background-color: {bg_color} !important;
            padding: 4px 8px !important;
            border-radius: 4px !important;
        }}
    </style>
</head>
<body>
    <div class="mermaid-container">
        <div class="mermaid">
{mermaid_code}
        </div>
    </div>
</body>
</html>
"""
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            # Let the browser determine natural size without viewport constraints
            page = browser.new_page()
            
            # Load the HTML
            page.set_content(html_content)
            
            # Wait for Mermaid to render - use smart waiting instead of fixed timeout
            # This waits for the actual SVG element to appear, which is much faster
            # than a hardcoded 4-second wait
            try:
                page.wait_for_selector('.mermaid svg', timeout=10000)  # 10s max
                # Give a small additional delay for any final rendering/animations
                page.wait_for_timeout(500)
                logging.debug("Flowchart SVG rendered successfully")
            except Exception as e:
                # Fallback: if selector wait fails, use the old timeout approach
                logging.warning(f"Smart wait failed ({e}), falling back to fixed timeout")
                page.wait_for_timeout(4000)
            
            # Screenshot the full page to capture entire flowchart without cropping
            page.screenshot(
                path=output_path,
                type='png',
                full_page=True  # Capture entire flowchart
            )
            
            browser.close()
            
        logging.info(f"Successfully generated flowchart at {output_path}")
        return True
        
    except ImportError:
        logging.warning("Playwright not installed. Install with: pip install playwright && playwright install chromium")
        return False
    except Exception as e:
        logging.error(f"Failed to generate flowchart with Playwright: {e}")
        return False


def generate_flowchart_with_api(mermaid_code: str, output_path: str, bg_color: str = "#ffffff") -> bool:
    """
    Generate flowchart PNG using Mermaid.ink API (fallback method).
    
    Args:
        mermaid_code: Mermaid diagram code
        output_path: Where to save the PNG
        bg_color: Background color (hex like '#0a192f' or '#ffffff')
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        import requests
        import base64
        import json
        
        # Prepare the Mermaid configuration
        config = {
            "theme": "base",
            "themeVariables": {
                "background": bg_color,
                "primaryColor": "#4A90E2",
                "primaryTextColor": "#fff",
                "primaryBorderColor": "#2E5C8A",
                "lineColor": "#8892b0" if bg_color.startswith("#0") else "#333333",
                "secondaryColor": "#50C878",
                "tertiaryColor": "#FFA500"
            }
        }
        
        # Create state object
        state = {
            "code": mermaid_code,
            "mermaid": config
        }
        
        # Encode to base64
        json_str = json.dumps(state)
        encoded = base64.urlsafe_b64encode(json_str.encode()).decode()
        
        # Call Mermaid.ink API
        url = f"https://mermaid.ink/img/{encoded}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Save the image
        with open(output_path, 'wb') as f:
            f.write(response.content)
        
        logging.info(f"Successfully generated flowchart using Mermaid.ink API at {output_path}")
        return True
        
    except ImportError:
        logging.warning("requests library not installed. Install with: pip install requests")
        return False
    except Exception as e:
        logging.error(f"Failed to generate flowchart with Mermaid.ink API: {e}")
        return False


def generate_flowchart_png(mermaid_code: str, output_path: str, bg_color: str = "#ffffff") -> bool:
    """
    Generate flowchart PNG using the best available method.
    
    Tries in order:
    1. Playwright (headless browser) - most reliable
    2. Mermaid.ink API - fallback
    
    Args:
        mermaid_code: Mermaid diagram code
        output_path: Where to save the PNG
        bg_color: Background color (hex like '#0a192f' or '#ffffff')
    
    Returns:
        bool: True if successful, False otherwise
    """
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Try Playwright first (best quality)
    if generate_flowchart_with_playwright(mermaid_code, output_path, bg_color):
        return True
    
    # Fallback to API
    logging.info("Trying Mermaid.ink API as fallback...")
    if generate_flowchart_with_api(mermaid_code, output_path, bg_color):
        return True
    
    logging.error("All flowchart generation methods failed")
    return False


if __name__ == "__main__":
    """CLI for generating flowcharts."""
    import argparse
    from reporting.flowchart import get_simulation_flowchart_detailed_mermaid
    
    parser = argparse.ArgumentParser(description="Generate flowchart PNGs from Mermaid code")
    parser.add_argument("--output", "-o", default="assets/simulation_flowchart.png", help="Output PNG path")
    parser.add_argument("--bg", choices=["dark", "white"], default="dark", help="Background style")
    args = parser.parse_args()
    
    # Determine background color
    bg_color = "#0a192f" if args.bg == "dark" else "#ffffff"
    
    # Get Mermaid code
    mermaid_code = get_simulation_flowchart_detailed_mermaid()
    
    # Generate
    success = generate_flowchart_png(mermaid_code, args.output, bg_color)
    
    if success:
        print(f"✅ Generated flowchart: {args.output}")
    else:
        print("❌ Failed to generate flowchart")
        print("Install Playwright: pip install playwright && playwright install chromium")
        print("Or install requests: pip install requests")
