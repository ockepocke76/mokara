"""
Debug script to test PDF generation and identify which table is causing issues.
Run this directly to bypass Streamlit caching.
"""
import sys
sys.path.insert(0, '/Users/oscarsverud/dev/btc_sim')

# Force reload of modules
if 'reporting.pdf' in sys.modules:
    del sys.modules['reporting.pdf']
if 'reporting.components' in sys.modules:
    del sys.modules['reporting.components']
if 'reporting.content' in sys.modules:
    del sys.modules['reporting.content']

from reporting.pdf import generate_pdf_report
import pandas as pd
from io import BytesIO

# Create minimal test data
params = {
    'simulation_name': 'test',
    'strategy': 'trinity',
    'all_params': {
        'num_years': 30,
        'initial_investment': 1000000,
        'strategy': 'trinity'
    }
}

stats = {
    'median_final_net_worth': 1500000,
    'success_rate': 0.95
}

# Empty dataframes for testing
average_results_df = pd.DataFrame()
median_yearly_results_df = pd.DataFrame()
example_path_df = pd.DataFrame()

try:
    print("Testing PDF generation...")
    pdf_buffer = generate_pdf_report(
        params=params,
        input_plot_buffers={},
        output_plot_buffers={},
        output_plot_keys=[],
        info_boxes=[],
        gemini_analysis_text="Test analysis",
        gemini_prompt_text="",
        data={},
        stats=stats,
        average_results_df=average_results_df,
        median_yearly_results_df=median_yearly_results_df,
        example_path_df=example_path_df,
        gemini_main_outcome_content="Test outcome",
        gemini_bottom_line_content="Test bottom line",
        to_buffer=True
    )
    print("✅ PDF generated successfully!")
    print(f"PDF size: {len(pdf_buffer.getvalue())} bytes")
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
