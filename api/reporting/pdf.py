import os
from datetime import datetime
import logging

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import inch
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak, Table, TableStyle
    from reportlab.platypus.tableofcontents import TableOfContents
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    from reportlab.lib import colors
    REPORTLAB_AVAILABLE = True
except ImportError as e:
    logging.error(f"Failed to import reportlab: {e}", exc_info=True)
    REPORTLAB_AVAILABLE = False

from .content import get_disclaimer_text, get_methodology_description, get_methodology_with_flowchart_content, get_strategic_analysis_content, get_glossary_data, get_section_intro, get_plot_description, get_structured_settings, INPUT_DATA_PLOT_ORDER, INPUT_DATA_APPENDIX_PLOTS, OUTPUT_PLOT_KEYS, CHAPTER_ORDER, APPENDIX_ORDER, REPORT_STRUCTURE # noqa
from .components import prepare_average_results_table, prepare_example_path_table, prepare_settings_table, prepare_advanced_stats_table, prepare_executive_summary, prepare_median_yearly_results_table, prepare_historical_stats_table

# --- Professional Styling --- #
DARK_BLUE = colors.HexColor('#003366')
DARK_GRAY = colors.HexColor('#333333')
LIGHT_GRAY = colors.HexColor('#F0F0F0')

class ReportDocTemplate(SimpleDocTemplate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.chapter_count = 0

    def afterFlowable(self, flowable):
        """Registers TOC entries."""
        if hasattr(flowable, 'toc_key'):
            text = flowable.getPlainText()
            level = 0
            self.notify('TOCEntry', (level, text, self.page, flowable.toc_key))

def _create_settings_table(data, title="Settings"):
    """Legacy function - redirects to generalized table creator."""
    from reporting.pdf_tables import create_styled_info_table
    return create_styled_info_table(data, title)

"""DEPRECATED - code below kept for reference only
Old implementation replaced by reporting.pdf_tables.create_styled_info_table()
"""
def _create_settings_table_old(data, title="Settings"):
    """Helper function to create a styled table for settings with professional formatting."""
    import logging
    from reportlab.lib.styles import getSampleStyleSheet
    
    styles = getSampleStyleSheet()
    
    # Validate data before creating table
    if not data:
        logging.warning("Attempted to create settings table with empty data")
        return Spacer(1, 0)  # Return empty spacer instead of creating table
    
    # Ensure all rows have exactly 2 columns and wrap text in Paragraphs for line breaking
    validated_data = []
    for i, row in enumerate(data):
        if not isinstance(row, (list, tuple)) or len(row) != 2:
            logging.warning(f"Row {i} has invalid format: {row}")
            continue
        # Wrap each cell in a Paragraph for proper text wrapping
        # Use <b> tag for first column to make it bold
        label = Paragraph(f'<b>{str(row[0])}</b>', styles['Normal'])
        value = Paragraph(str(row[1]), styles['Normal'])
        validated_data.append([label, value])
    
    if not validated_data:
        logging.warning("No valid rows after validation")
        return Spacer(1, 0)
    
    # Add title header row with white text
    title_para = Paragraph(f'<b><font color="white">{title}</font></b>', styles['Normal'])
    table_data = [[title_para, ""]] + validated_data
    
    table = Table(table_data, colWidths=[3.0 * inch, 2.8 * inch])
    style = TableStyle([
        ('SPAN', (0, 0), (1, 0)),  # Span the title across two columns
        ('BACKGROUND', (0, 0), (1, 0), DARK_BLUE),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),  # Align to top for multi-line cells
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),  # Bold for the first column (title)
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ])
    table.setStyle(style)
    return table

def _create_summary_table(data, title):
    """Legacy function - redirects to generalized table creator."""
    from reporting.pdf_tables import create_styled_info_table
    return create_styled_info_table(data, title)

"""DEPRECATED - code below kept for reference only
Old implementation replaced by reporting.pdf_tables.create_styled_info_table()
"""
def _create_summary_table_old(data, title):
    """Helper function to create a styled table for summary info boxes."""
    import logging
    
    logging.info(f"Creating summary table: {title}")
    logging.info(f"Data type: {type(data)}, Data length: {len(data) if isinstance(data, (list, dict)) else 'N/A'}")
    
    if isinstance(data, list):
        logging.info(f"First few items: {data[:3] if len(data) > 0 else 'empty'}")
    
    # Validate data
    if not data:
        logging.warning(f"Empty data for table '{title}'")
        return Spacer(1, 0)
    
    # Ensure data is a list of dicts with 'label' and 'value'
    if not isinstance(data, list):
        logging.error(f"Data for '{title}' is not a list: {type(data)}")
        return Spacer(1, 0)
    
    table_data = [[f'<font color="white"><b>{title}</b></font>', ""]]  # Header row with white text
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            logging.warning(f"Item {i} in '{title}' is not a dict: {type(item)}")
            continue
        label = str(item.get('label', ''))
        value = str(item.get('value', ''))
        if label or value:
            table_data.append([label, value])
    
    if len(table_data) < 2:
        logging.warning(f"No valid rows for table '{title}'")
        return Spacer(1, 0)
    
    logging.info(f"Creating table '{title}' with {len(table_data)} rows")
    table = Table(table_data, colWidths=[3.0 * inch, 2.8 * inch])
    style = TableStyle([
        ('SPAN', (0, 0), (1, 0)), # Span the title across two columns
        ('BACKGROUND', (0, 0), (1, 0), DARK_BLUE),
        ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'), # Bold for the first column
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
    ])
    table.setStyle(style)
    return table

def get_settings_chapter_content(params, styles):
    """Creates a list of flowables for the detailed settings chapter using structured data."""
    content = []
    import logging
    
    # Logic moved to prepare_settings_table in reporting/components.py
    # This keeps the call site clean and logic centralized.
    logging.info(f"PDF Params Keys (Raw): {list(params.keys())[:20]}...") 

    # prepare_settings_table returns a list of dicts with 'title' and 'metrics' keys
    # robust handling of nested vs flat params is now inside this function.
    structured_settings = prepare_settings_table(params)
    
    logging.info(f"PDF Structured Settings Sections: {[s.get('title') for s in structured_settings]}")

    for section in structured_settings:
        section_title = section.get('title', '')
        section_metrics = section.get('metrics', [])
        
        if not section_metrics:
            logging.warning(f"PDF: Section '{section_title}' has no metrics.")
            continue
            
        content.append(Paragraph(section_title, styles['H3']))
        # Convert metrics list to table data format with defensive checks
        table_data = []
        for metric in section_metrics:
            # Ensure each metric has both label and value
            label = str(metric.get('label', ''))
            value = str(metric.get('value', ''))
            if label or value:  # Only add if at least one field has content
                table_data.append([label, value])
        
        # Only create table if we have data
        if table_data:
            content.append(_create_settings_table(table_data, "Asset Information"))
            content.append(Spacer(1, 12))
        
    return content
 
def get_advanced_stats_appendix_content(stats, params, styles):
    """Creates the content for the Advanced Statistics appendix."""
    content = []
    intro_text = get_section_intro("Advanced Statistics Appendix")
    content.append(Paragraph(intro_text, styles['Justify']))
    content.append(Spacer(1, 12))

    # Add the info box explaining the difference between Asset and Strategy ratios
    info_box_text = get_section_intro("Advanced Statistics Appendix Info Box")
    content.append(Paragraph(info_box_text, styles['InfoBox']))
    content.append(Spacer(1, 18))
    
    metrics_to_display = prepare_advanced_stats_table(stats, params)

    for metric in metrics_to_display:
        content.append(Paragraph(f"<b>{metric['name']}:</b> {metric['value_str']}", styles['H3']))
        content.append(Paragraph(metric['definition'], styles['Justify']))
        content.append(Spacer(1, 6))
        content.append(Paragraph(f"<b>In This Simulation:</b> {metric['sim_context']}", styles['Justify']))
        content.append(Spacer(1, 6))
        content.append(Paragraph(f"<b>Real-World Context:</b> {metric['real_world']}", styles['Justify']))
        content.append(Spacer(1, 12))
        
    return content

def get_example_path_table_content(example_path_df, params, styles, currency='SEK'):
    """Creates the content for the Example Simulation Path appendix."""
    content = []
    sim_index = example_path_df.attrs.get('sim_index', 'N/A')
    intro_text = get_section_intro("Example Simulation Path Appendix").replace("a single, randomly selected simulation path", f"a single, randomly selected simulation path (Run #{sim_index})")
    content.append(Paragraph(intro_text, styles['Justify']))
    content.append(Paragraph(f"<i>All values in thousands of {currency} unless otherwise noted.</i>", styles['Justify']))
    content.append(Spacer(1, 12))

    # Use the centralized function to get the pre-formatted DataFrame
    df_for_table = prepare_example_path_table(example_path_df)

    if df_for_table.empty:
        content.append(Paragraph("No example path data available.", styles['Justify']))
        return content
    # Convert DataFrame to list of lists for ReportLab Table
    data = [df_for_table.columns.tolist()] + df_for_table.values.tolist()
    
    # Validate table data
    if not data or len(data) < 2:  # Need at least header + 1 row
        content.append(Paragraph("Insufficient data for table.", styles['Justify']))
        return content
    
    # Ensure all rows have the same number of columns
    num_cols = len(data[0])
    data = [row for row in data if len(row) == num_cols]
    
    if len(data) < 2:
        content.append(Paragraph("Table data has inconsistent columns.", styles['Justify']))
        return content

    # Create and style the table
    table = Table(data, hAlign='LEFT')
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')), # Header background
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'), # Align 'Year' column to the left
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F0F0F0')),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ])
    table.setStyle(style)
    content.append(table)
    return content

def _apply_red_text_to_table_style(data, style_cmds):
    """Helper to add red text color for negative values to a TableStyle list."""
    from reportlab.lib import colors
    # data includes header at row 0
    for r_idx, row in enumerate(data):
        if r_idx == 0: continue
        for c_idx, val in enumerate(row):
             s = str(val)
             if s.strip().startswith('-') or s.strip().startswith('-$') or s.strip().startswith('-SEK'):
                 style_cmds.append(('TEXTCOLOR', (c_idx, r_idx), (c_idx, r_idx), colors.HexColor('#ef4444')))
    return style_cmds

def get_average_results_table_content(average_results_df, params, styles, currency='SEK'):
    """Creates the content for the Average Yearly Results appendix."""
    content = []
    intro_text = get_section_intro("Average Yearly Results Appendix")
    content.append(Paragraph(intro_text, styles['Justify']))
    content.append(Paragraph(f"<i>All values in thousands of {currency} unless otherwise noted.</i>", styles['Justify'])) # Explicitly state units
    content.append(Spacer(1, 12))

    # Use the centralized function to get the pre-formatted DataFrame
    df_for_table = prepare_average_results_table(average_results_df)

    if df_for_table.empty:
        content.append(Paragraph("No average results data available.", styles['Justify']))
        return content

    # Convert DataFrame to list of lists for ReportLab Table
    data = [df_for_table.columns.tolist()] + df_for_table.values.tolist()
    
    # Validate table data
    if not data or len(data) < 2:
        content.append(Paragraph("Insufficient data for table.", styles['Justify']))
        return content
    
    # Ensure all rows have the same number of columns
    num_cols = len(data[0])
    data = [row for row in data if len(row) == num_cols]
    
    if len(data) < 2:
        content.append(Paragraph("Table data has inconsistent columns.", styles['Justify']))
        return content

    # Create and style the table
    table = Table(data, hAlign='LEFT')
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')), # Header background
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'), # Align 'Year' column to the left
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F0F0F0')),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]
    # Apply red text for negative values
    style_cmds = _apply_red_text_to_table_style(data, style_cmds)
    
    style = TableStyle(style_cmds)
    table.setStyle(style)
    content.append(table)
    return content

def get_median_yearly_results_table_content(median_yearly_results_df, params, styles, currency='SEK'):
    """Creates the content for the Median Yearly Results appendix."""
    content = []
    intro_text = get_section_intro("Median Yearly Results Appendix")
    content.append(Paragraph(intro_text, styles['Justify']))
    content.append(Paragraph(f"<i>All values in thousands of {currency} unless otherwise noted.</i>", styles['Justify'])) # Explicitly state units
    content.append(Spacer(1, 12))

    # Use the centralized function to get the pre-formatted DataFrame
    df_for_table = prepare_median_yearly_results_table(median_yearly_results_df)

    if df_for_table.empty:
        content.append(Paragraph("No median yearly results data available.", styles['Justify']))
        return content

    # Convert DataFrame to list of lists for ReportLab Table
    data = [df_for_table.columns.tolist()] + df_for_table.values.tolist()
    
    # Validate table data
    if not data or len(data) < 2:
        content.append(Paragraph("Insufficient data for table.", styles['Justify']))
        return content
    
    # Ensure all rows have the same number of columns
    num_cols = len(data[0])
    data = [row for row in data if len(row) == num_cols]
    
    if len(data) < 2:
        content.append(Paragraph("Table data has inconsistent columns.", styles['Justify']))
        return content

    # Create and style the table
    table = Table(data, hAlign='LEFT')
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#003366')), # Header background
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (0, -1), 'LEFT'), # Align 'Year' column to the left
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#F0F0F0')),
        ('GRID', (0, 0), (-1, -1), 1, colors.black)
    ]
    # Apply red text for negative values
    style_cmds = _apply_red_text_to_table_style(data, style_cmds)
    
    style = TableStyle(style_cmds)
    table.setStyle(style)
    content.append(table)
    return content

def get_input_data_analysis_content(params, plot_buffers, styles, data):
    """Creates the content for the Input Data Analysis chapter."""
    width, _ = A4
    content = []
    intro_text = get_section_intro("Input Data Analysis")
    content.append(Paragraph(intro_text, styles['Justify']))
    content.append(Spacer(1, 12))


    # Add the historical stats table
    historical_stats = data.get('historical_stats', {})
    if historical_stats:
        # Add section header for the asset information table
        content.append(Paragraph("<b>Asset Information</b>", styles['H3']))
        content.append(Spacer(1, 6))
        table_data = prepare_historical_stats_table(historical_stats, params)
        if table_data:  # Only create table if we have data
            # Convert from dict format to list format for _create_settings_table
            table_data_list = [[item['label'], item['value']] for item in table_data]
            table = _create_settings_table(table_data_list, "Asset Information")
            content.append(table)
            content.append(Spacer(1, 24))

    # The plot_buffers are now guaranteed to be in the correct order from main.py.
    # We just need to map them to the keys from our single source of truth.
    for i, plot_buffer in enumerate(plot_buffers):
        img = Image(plot_buffer, width=width - 2*inch, height=(width - 2*inch)*(3/4))
        content.append(img)
        content.append(Spacer(1, 6))
        
        description_key = INPUT_DATA_PLOT_ORDER[i]
        description_text = get_plot_description(description_key)
        content.append(Paragraph(description_text, styles['Justify']))
        content.append(Spacer(1, 24))

    return content

def get_input_data_appendix_content(params, plot_buffers, styles, data):
    """Creates the content for the Input Data Analysis Appendix (Technical Charts)."""
    from reportlab.platypus import Image
    from reportlab.lib.units import inch
    
    width, _ = A4
    content = []
    
    # Iterate plot buffers using INPUT_DATA_APPENDIX_PLOTS keys
    if not plot_buffers:
         # Use a placeholder message if no charts provided
         content.append(Paragraph("No technical charts available for this simulation.", styles['Justify']))
         return content

    for i, plot_buffer in enumerate(plot_buffers):
        img = Image(plot_buffer, width=width - 2*inch, height=(width - 2*inch)*(3/4))
        content.append(img)
        content.append(Spacer(1, 6))
        
        # Determine description key
        # Assuming buffers match INPUT_DATA_APPENDIX_PLOTS order
        if i < len(INPUT_DATA_APPENDIX_PLOTS):
            description_key = INPUT_DATA_APPENDIX_PLOTS[i]
            description_text = get_plot_description(description_key)
            if description_text:
                content.append(Paragraph(description_text, styles['Justify']))
        content.append(Spacer(1, 24))
    
    return content

def get_strategic_analysis_chapter_content(params, styles):
    """Creates the content for the Strategic Analysis chapter."""
    from reportlab.platypus import Image
    from reportlab.lib.units import inch
    from reporting.generate_flowchart import generate_flowchart_png
    from reporting.strategy_flowcharts import get_strategy_flowchart
    import os
    
    content = []
    
    # Get the structured content from the centralized function
    strategic_content = get_strategic_analysis_content(params)
    
    # Add intro text
    content.append(Paragraph(strategic_content['intro'], styles['Justify']))
    content.append(Spacer(1, 18))
    
    # Add transaction types table
    content.append(Paragraph("<b>Available Transaction Types</b>", styles['H3']))
    content.append(Spacer(1, 6))
    transaction_data = [[t['label'], t['value']] for t in strategic_content['transaction_types']]
    transaction_table = _create_settings_table(transaction_data, "Available Actions")
    content.append(transaction_table)
    content.append(Spacer(1, 24))
    
    # Add strategy-specific description
    content.append(Paragraph("<b>Strategy Used in This Simulation</b>", styles['H3']))
    content.append(Spacer(1, 6))
    content.append(Paragraph(strategic_content['strategy_description'], styles['Justify']))
    content.append(Spacer(1, 18))
    
    # Add strategy flowchart if available (using centralized flowchart_info)
    flowchart_info = strategic_content.get('flowchart_info', {})
    
    if flowchart_info.get('available'):
        flowchart_path = flowchart_info['white_path']
        
        # Generate white background version for PDF if it doesn't exist
        if flowchart_info.get('needs_generation_white', False):
            from reporting.strategy_flowcharts import get_strategy_flowchart
            mermaid_code = get_strategy_flowchart(flowchart_info['key'], theme='light')
            generate_flowchart_png(mermaid_code, flowchart_path, bg_color='#ffffff')
        
        if os.path.exists(flowchart_path):
            content.append(Paragraph("<b>Strategy Decision Flow</b>", styles['H3']))
            content.append(Spacer(1, 6))
            content.append(Paragraph(
                "The following diagram illustrates simplified annual decision-making logic of this strategy:",
                styles['Normal']
            ))
            content.append(Spacer(1, 12))
            
            # Add flowchart image - maintain aspect ratio
            img = Image(flowchart_path, width=5.5*inch, height=5.5*inch)
            content.append(img)
    
    # --- Strategy Evaluation Section ---
    # Use evaluation data from centralized strategic_content
    try:
        from reporting.strategy_evaluation_charts import generate_evaluation_radar_chart_png
        import json
        
        strategy_key = params.get('strategy', '')
        # Convert snake_case to display name, preferring custom name if available
        if strategy_key == 'custom_strategy':
             strategy_display = params.get('custom_strategy_name', 'Custom Strategy')
        else:
             strategy_display = ' '.join(word.capitalize() for word in strategy_key.split('_'))
        
        evaluation_data = strategic_content.get('evaluation_data')
        
        if evaluation_data:
            content.append(Spacer(1, 24))
            content.append(Paragraph("<b>Strategy Evaluation Results</b>", styles['H3']))
            content.append(Spacer(1, 6))
            
            # --- Added Market Scenarios Table (Parity with UI) ---
            from reporting.components import prepare_market_scenarios_table
            scenarios_data = prepare_market_scenarios_table()
            scenarios_table = _create_settings_table(scenarios_data, "Market Scenarios (Stress Test Definitions)")
            content.append(scenarios_table)
            content.append(Spacer(1, 12))
            
            content.append(Paragraph(
                "This strategy has been stress-tested across these 8 standardized market scenarios. "
                "The following metrics show how it performs based on the collective leaderboard evaluation.",
                styles['Normal']
            ))
            content.append(Spacer(1, 6))
            
            # Excellence Score highlight
            excellence_score = evaluation_data.get('excellence_score', 0)
            content.append(Paragraph(
                f"<b>Excellence Score: {excellence_score:.1f}/100</b>",
                styles['H3']
            ))
            content.append(Spacer(1, 12))
            
            # Generate radar chart
            radar_buffer = generate_evaluation_radar_chart_png(strategy_display, evaluation_data)
            if radar_buffer:
                radar_img = Image(radar_buffer, width=4*inch, height=4*inch)
                content.append(radar_img)
                content.append(Spacer(1, 12))
            
            # Component Scores table
            from core.strategy_evaluation import METRIC_WEIGHTS
            
            component_data = []
            for key, info in METRIC_WEIGHTS.items():
                if info['weight'] > 0:
                    score = evaluation_data.get(key, 0)
                    weight_pct = int(info['weight'] * 100)
                    component_data.append([f"{info['name']} ({weight_pct}% weight)", f"{score:.0f}/100"])
            
            if component_data:
                content.append(Paragraph("<b>Component Scores</b>", styles['H3']))
                content.append(Spacer(1, 6))
                component_table = _create_settings_table(component_data, "Score Breakdown")
                content.append(component_table)
                content.append(Spacer(1, 12))
            
            # Scenario Performance table
            scenario_json = evaluation_data.get('scenario_results_json')
            if scenario_json:
                scenario_data = json.loads(scenario_json) if isinstance(scenario_json, str) else scenario_json
                
                content.append(Paragraph("<b>Performance by Scenario</b>", styles['H3']))
                content.append(Spacer(1, 6))
                
                scenario_table_data = []
                for scenario in scenario_data:
                    name = scenario.get('name', 'Unknown')
                    sortino = scenario.get('sortino_ratio', 0)
                    success = scenario.get('success_rate', 0) * 100
                    scenario_table_data.append([name, f"{sortino:.2f}", f"{success:.1f}%"])
                
                if scenario_table_data:
                    # Add header
                    scenario_table_data.insert(0, ['Scenario', 'Sortino Ratio', 'Success Rate'])
                    scenario_table = Table(scenario_table_data, colWidths=[2.5*inch, 1.5*inch, 1.5*inch])
                    scenario_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), DARK_BLUE),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
                        ('TOPPADDING', (0, 0), (-1, 0), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                    ]))
                    content.append(scenario_table)
        else:
            # No evaluation data available
            content.append(Spacer(1, 12))
            content.append(Paragraph(
                "<i>Note: This strategy has not yet been evaluated on the leaderboard. "
                "Evaluation data will appear here once the strategy is tested.</i>",
                styles['Normal']
            ))
    except Exception as e:
        logging.warning(f"Could not add strategy evaluation to PDF: {e}")
    
    return content

def get_executive_summary_content(params, stats, styles, gemini_content, verdict_plot_buffer=None, currency='SEK'):
    """Creates the content for the Executive Summary chapter."""
    from reportlab.platypus import Image
    from reportlab.lib.units import inch
    
    content = []
    
    # Use the centralized function to get the prepared summary content
    summary_content = prepare_executive_summary(params, stats, gemini_content, currency=currency)

    content.append(Paragraph(summary_content['scenario'], styles['Justify']))
    content.append(Spacer(1, 12))
    content.append(Paragraph(summary_content['main_outcome'], styles['Justify']))
    content.append(Spacer(1, 12))
    
    # Convert key_stats list to a formatted table
    key_stats_data = [[stat['label'], stat['value']] for stat in summary_content['key_stats']]
    key_stats_table = _create_settings_table(key_stats_data, "Key Statistics")
    content.append(key_stats_table)
    content.append(Spacer(1, 12))
    
    # Verdict Gauge Image (if available)
    if verdict_plot_buffer:
        # Gauge is nominally 600x350
        # Fit to page width (approx 6 inch usable)
        # 6 inch width -> height = 3.5 inch
        img_width = 5.5 * inch
        img_height = img_width * (350 / 600)
        
        img = Image(verdict_plot_buffer, width=img_width, height=img_height)
        content.append(img)
        content.append(Spacer(1, 12))
    
    content.append(Paragraph(summary_content['bottom_line'], styles['Justify']))

    return content

def generate_pdf_report(params, input_plot_buffers, output_plot_buffers, output_plot_keys, info_boxes, gemini_analysis_text, gemini_prompt_text, data, stats, average_results_df, median_yearly_results_df, example_path_df, gemini_main_outcome_content, gemini_bottom_line_content, appendix_plot_buffers=None, verdict_plot_buffer=None, to_buffer=False):
    logging.info("Generating PDF report...")
    
    # Extract currency from simulation parameters (with fallback for legacy simulations)
    from core.simulation_currency import get_simulation_currency
    currency = get_simulation_currency(params)
    logging.info(f"PDF Report: Using currency {currency} for this simulation")
    
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    report_name_prefix = params.get('simulation_name', 'simulation_report')
    
    reports_dir = "pdfreports"
    os.makedirs(reports_dir, exist_ok=True)
    base_filename = f"{report_name_prefix}_{timestamp_str}.pdf"
    filename = os.path.join(reports_dir, base_filename)

    # If generating to a buffer, create a BytesIO object
    if to_buffer:
        from io import BytesIO
        buffer = BytesIO()
    
    styles = getSampleStyleSheet()
    
    body_font = 'Helvetica'
    bold_font = 'Helvetica-Bold'
    heading_font = 'Times-Bold'

    if 'Justify' not in styles: styles.add(ParagraphStyle(name='Justify', fontName=body_font, alignment=TA_JUSTIFY, fontSize=10, leading=14))
    if 'Center' not in styles: styles.add(ParagraphStyle(name='Center', fontName=body_font, alignment=TA_CENTER))
    if 'H1' not in styles: styles.add(ParagraphStyle(name='H1', fontName=heading_font, fontSize=24, alignment=TA_CENTER, spaceAfter=18, textColor=DARK_BLUE, leading=30))
    if 'H2' not in styles: styles.add(ParagraphStyle(name='H2', fontName=heading_font, fontSize=16, spaceBefore=12, spaceAfter=6, textColor=DARK_BLUE, leading=20))
    if 'H3' not in styles: styles.add(ParagraphStyle(name='H3', fontName=bold_font, fontSize=12, spaceBefore=12, spaceAfter=4, textColor=DARK_GRAY))
    if 'SubTitle' not in styles: styles.add(ParagraphStyle(name='SubTitle', fontName=body_font, fontSize=12, alignment=TA_CENTER, spaceAfter=24, textColor=DARK_GRAY))
    if 'Code' not in styles: styles.add(ParagraphStyle(name='Code', fontName='Courier', fontSize=8, leading=10, backColor=LIGHT_GRAY, padding=5))
    if 'InfoBox' not in styles: styles.add(ParagraphStyle(name='InfoBox', fontName=body_font, fontSize=9, leading=12, backColor=colors.HexColor('#E8F4FD'), borderColor=colors.HexColor('#B0C4DE'), borderWidth=1, padding=10, borderRadius=5, spaceAfter=6))
    if 'TOCHeading1' not in styles: styles.add(ParagraphStyle(name='TOCHeading1', fontName=heading_font, fontSize=14, leftIndent=20, spaceBefore=10, textColor=DARK_BLUE))
    if 'TOCHeading2' not in styles: styles.add(ParagraphStyle(name='TOCHeading2', fontName=heading_font, fontSize=12, leftIndent=40, spaceBefore=6, textColor=DARK_BLUE))

    width, height = A4

    doc = ReportDocTemplate(buffer if to_buffer else filename, pagesize=A4, leftMargin=inch, rightMargin=inch, topMargin=inch, bottomMargin=inch)
    story = []

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(body_font, 9)
        canvas.setFillColor(DARK_GRAY)
        canvas.drawString(inch, 0.75 * inch, f"MyMonteCarlo - Financial Simulation & Strategy Report | Page {doc.page}")
        canvas.drawRightString(doc.width + doc.leftMargin, 0.75 * inch, "Strictly Private and Confidential")
        canvas.setStrokeColor(DARK_BLUE)
        canvas.setLineWidth(2)
        canvas.line(inch, height - 0.5 * inch, width + inch - inch, height - 0.5 * inch)
        canvas.restoreState()

    story.append(Paragraph("Financial Simulation & Strategy Report", styles['H1']))
    story.append(Spacer(1, 0.5 * inch))
    story.append(Spacer(1, 0.5 * inch))
    
    # improved strategy display name logic
    raw_strategy_key = params.get('strategy', '')
    if raw_strategy_key == 'custom_strategy':
        strategy_display = params.get('custom_strategy_name', 'Custom Strategy')
    else:
        strategy_display = ' '.join(word.capitalize() for word in raw_strategy_key.split('_'))
        
    # Use .get() for robustness, in case 'asset_name' is missing from older simulation data.
    asset_name = params.get("asset_name", "the selected asset")
    num_years = params.get("num_years", "an unknown number of")
    subtitle = f'A Monte Carlo Analysis of the {strategy_display} Strategy with {asset_name} over {num_years} Years'
    story.append(Paragraph(subtitle, styles['SubTitle']))
    story.append(Paragraph(f"Date of Generation: {datetime.now().strftime('%B %d, %Y')}", styles['SubTitle']))
    
    # Add the simulation paths plot to the title page (log version, index 0 in output_plot_buffers)
    # Create a map of plots for easy access by key
    plot_map = {}
    if output_plot_buffers and output_plot_keys:
        for i, key in enumerate(output_plot_keys):
            if i < len(output_plot_buffers):
                plot_map[key] = output_plot_buffers[i]
    
    # Add the simulation paths plot to the title page (log version)
    # We prefer the 'simulation_paths_log' plot, but fall back to the first available if missing
    title_page_img = None
    if 'simulation_paths_log' in plot_map:
        title_page_img = plot_map['simulation_paths_log']
    elif len(output_plot_buffers) > 0:
        title_page_img = output_plot_buffers[0]
        
    if title_page_img:
        img = Image(title_page_img, width=width - 2*inch, height=(width - 2*inch)*(9/16))
        story.append(img)
    story.append(PageBreak())

    toc = TableOfContents()
    toc.levelStyles = [styles['TOCHeading1'], styles['TOCHeading2']]
    story.append(Paragraph("Table of Contents", styles['H1']))
    story.append(toc)
    story.append(PageBreak())

    # --- Assemble the Simulation Summary chapter content ---
    summary_content = [
        Paragraph(get_section_intro("Simulation Summary"), styles['Justify'])
    ]
    
    # Plot map is already created above

    # Helper to parse info_boxes (dict or list)
    outcome_table = None
    risk_table = None
    psych_table = None
    
    if isinstance(info_boxes, dict):
        outcome_table = info_boxes.get('outcome')
        risk_table = info_boxes.get('risk')
        psych_table = info_boxes.get('psychological')
    elif isinstance(info_boxes, list) and len(info_boxes) >= 2:
        outcome_table = info_boxes[0]
        risk_table = info_boxes[1]
    
    # --- 1. Outcome Section ---
    if outcome_table:
        summary_content.append(Spacer(1, 12))
        summary_content.append(_create_summary_table(outcome_table, f"Outcome Analysis (Yr {params.get('num_years', 'N/A')})"))
    
    # Portfolio Value Overview Plot
    if 'portfolio_value_overview' in plot_map:
        summary_content.append(Spacer(1, 12))
        img = Image(plot_map['portfolio_value_overview'], width=width - 2*inch, height=(width - 2*inch)*(9/16))
        summary_content.append(img)
        summary_content.append(Spacer(1, 6))
        summary_content.append(Paragraph(get_plot_description('portfolio_value_overview'), styles['Justify']))

    # Final Net Worth Distribution Plot
    if 'final_net_worth_distribution_bbd' in plot_map:
        summary_content.append(Spacer(1, 12))
        img = Image(plot_map['final_net_worth_distribution_bbd'], width=width - 2*inch, height=(width - 2*inch)*(9/16))
        summary_content.append(img)
        summary_content.append(Spacer(1, 6))
        summary_content.append(Paragraph(get_plot_description('final_net_worth_distribution_bbd'), styles['Justify']))
        
    # --- 2. Risk Section ---
    if risk_table:
        summary_content.append(Spacer(1, 24))
        summary_content.append(_create_summary_table(risk_table, "Risk Analysis"))

    # Survival Curve Plot
    if 'survival_curve' in plot_map:
        summary_content.append(Spacer(1, 12))
        img = Image(plot_map['survival_curve'], width=width - 2*inch, height=(width - 2*inch)*(9/16))
        summary_content.append(img)
        summary_content.append(Spacer(1, 6))
        summary_content.append(Paragraph(get_plot_description('survival_curve'), styles['Justify']))

    # --- 3. Psychological / Path Section ---
    if psych_table:
        summary_content.append(Spacer(1, 24))
        summary_content.append(_create_summary_table(psych_table, "Psychological Stress Indicators"))

    # Simulation Paths Plot
    if 'simulation_paths_log' in plot_map:
        summary_content.append(Spacer(1, 12))
        img = Image(plot_map['simulation_paths_log'], width=width - 2*inch, height=(width - 2*inch)*(9/16))
        summary_content.append(img)
        summary_content.append(Spacer(1, 6))
        summary_content.append(Paragraph(get_plot_description('simulation_paths_log'), styles['Justify']))

    # --- 4. Mechanics & Advanced Stats Section ---
    summary_content.append(Spacer(1, 24))
    
    advanced_stats_data = [
        ["Asset Sharpe Ratio", f"{stats.get('asset_sharpe_ratio', 0.0):.2f}"],
        ["Asset Sortino Ratio", f"{stats.get('asset_sortino_ratio', 0.0):.2f}"],
        ["Strategy Sharpe Ratio", f"{stats.get('strategy_sharpe_ratio', 0.0):.2f}"],
        ["Strategy Sortino Ratio", f"{stats.get('strategy_sortino_ratio', 0.0):.2f}"],
    ]
    summary_content.append(_create_settings_table(advanced_stats_data, "Advanced Statistics Summary (see appendix for details)"))

    # Cash Flow & Liabilities Plot
    if 'cashflow_liabilities' in plot_map:
        summary_content.append(Spacer(1, 12))
        img = Image(plot_map['cashflow_liabilities'], width=width - 2*inch, height=(width - 2*inch)*(9/16))
        summary_content.append(img)
        summary_content.append(Spacer(1, 6))
        summary_content.append(Paragraph(get_plot_description('cashflow_liabilities'), styles['Justify']))

    # Yearly Cash Flow Plot
    if 'yearly_cash_flow' in plot_map:
        summary_content.append(Spacer(1, 12))
        img = Image(plot_map['yearly_cash_flow'], width=width - 2*inch, height=(width - 2*inch)*(9/16))
        summary_content.append(img)
        summary_content.append(Spacer(1, 6))
        summary_content.append(Paragraph(get_plot_description('yearly_cash_flow'), styles['Justify']))
    
    # --- Build data context for manifest-driven rendering ---
    from reporting.pdf_manifest_renderer import render_section_for_pdf
    from reporting.components import prepare_settings_table
    
    # Prepare settings table with logging
    logging.info(f"PDF Context: params keys = {list(params.keys())[:20]}")
    settings_table_data = prepare_settings_table(params)
    logging.info(f"PDF Context: settings_table has {len(settings_table_data)} sections")
    for section in settings_table_data:
        logging.info(f"  Section '{section.get('title')}': {len(section.get('metrics', []))} metrics")
    
    pdf_context = {
        # Core data
        'disclaimer': get_disclaimer_text(),
        'params': params,
        'stats': stats,
        'currency': currency,
        
        # Settings
        'settings_table': settings_table_data,
        
        # AI content
        'gemini_analysis': gemini_analysis_text,
        'gemini_main_outcome': gemini_main_outcome_content,
        'gemini_bottom_line': gemini_bottom_line_content,
        
        # Advanced stats
        'advanced_stats': prepare_advanced_stats_table(stats, params),
        
        # Results dataframes
        'average_results': average_results_df,
        'median_results': median_yearly_results_df,
        'example_path': example_path_df,
        
        # Glossary
        'glossary': get_glossary_data(),
    }
    
    # --- Assemble chapter content using manifest rendering ---
    all_chapters = {}
    
    # For sections not yet using manifest, keep old approach
    # (Methodology, Strategic Analysis, Input Data, Simulation Summary have complex content)
    all_chapters["Methodology Overview"] = get_methodology_with_flowchart_content(styles)
    all_chapters["Strategic Analysis"] = get_strategic_analysis_chapter_content(params, styles)
    all_chapters["Input Data Analysis"] = get_input_data_analysis_content(params, input_plot_buffers, styles, data) if input_plot_buffers else []
    all_chapters["Simulation Summary"] = summary_content
    all_chapters["Executive Summary"] = get_executive_summary_content(
        params, stats, styles,
        {'main_outcome': gemini_main_outcome_content, 'bottom_line': gemini_bottom_line_content},
        verdict_plot_buffer=verdict_plot_buffer,
        currency=currency
    )
    
    # For simple sections, use manifest rendering
    for section_name, items in REPORT_STRUCTURE.items():
        if section_name.startswith('Appendices:'):
            continue  # Handle appendices separately below
            
        # Skip sections we're still doing the old way
        if section_name in ["Methodology Overview", "Strategic Analysis", "Input Data Analysis", 
                           "Simulation Summary", "Executive Summary"]:
            continue
            
        # Use manifest rendering for simple sections
        section_content = []
        render_section_for_pdf(section_name, items, pdf_context, section_content, styles)
        all_chapters[section_name] = section_content

    # --- Build the story by iterating through REPORT_STRUCTURE (manifest-driven) ---
    # NOTE: We now use REPORT_STRUCTURE as the authoritative order instead of CHAPTER_ORDER
    chapter_count = 0
    
    # Map of section names from REPORT_STRUCTURE to their content
    section_to_content = {
        "Important Disclaimer": all_chapters.get("Important Disclaimer", []),
        "Simulation Settings": all_chapters.get("Simulation Settings", []),
        "Methodology Overview": all_chapters.get("Methodology Overview", []),
        "Strategic Analysis": all_chapters.get("Strategic Analysis", []),
        "Input Data Analysis": all_chapters.get("Input Data Analysis", []),
        "Simulation Summary": all_chapters.get("Simulation Summary", []),
        "Executive Summary": all_chapters.get("Executive Summary", []),
        "Qualitative Analysis": all_chapters.get("Qualitative Analysis", [])
    }
    
    # Iterate through REPORT_STRUCTURE to maintain order
    section_index = 0
    for section_name in REPORT_STRUCTURE.keys():
        # Skip appendices (handled separately below)
        if section_name.startswith('Appendices:'):
            continue
            
        # Get content for this section
        content = section_to_content.get(section_name, [])
        
        if content:
            chapter_count += 1
            section_index += 1
            
            # Special case for a more descriptive title
            display_title = "Strategic Analysis: Asset Withdrawal vs. Loan Drawdown" if section_name == "Strategic Analysis" else section_name
            
            key = f"chap{chapter_count}"
            p = Paragraph(f'<a name="{key}"/>{section_index}. {display_title}', styles['H2'])
            p.toc_key = key
            story.append(p)
            story.extend(content)
            story.append(PageBreak())

    # --- Assemble all appendix content ---
    all_appendices = {}

    # Glossary
    glossary_content = []
    for group_title, terms in get_glossary_data().items():
        glossary_content.append(Paragraph(group_title, styles['H3']))
        glossary_content.append(Spacer(1, 6))
        for term, definition in sorted(terms.items()):
            glossary_content.append(Paragraph(f"<b>{term}</b>", styles['Normal']))
            glossary_content.append(Paragraph(definition, styles['Justify']))
            glossary_content.append(Spacer(1, 6))
        glossary_content.append(Spacer(1, 12))
    
    all_appendices['Advanced Statistics'] = get_advanced_stats_appendix_content(stats, params, styles)
    if average_results_df is not None and not average_results_df.empty:
        all_appendices['Average Yearly Results'] = get_average_results_table_content(average_results_df, params, styles, currency=currency)
    if median_yearly_results_df is not None and not median_yearly_results_df.empty:
        all_appendices['Median Yearly Results'] = get_median_yearly_results_table_content(median_yearly_results_df, params, styles, currency=currency)
    if example_path_df is not None and not example_path_df.empty:
        all_appendices['Example Simulation Path'] = get_example_path_table_content(example_path_df, params, styles, currency=currency)
    
    if example_path_df is not None and not example_path_df.empty:
        all_appendices['Example Simulation Path'] = get_example_path_table_content(example_path_df, params, styles, currency=currency)
    
    # Input Data Analysis Appendix (Technical Charts)
    # This was moved from main body to appendix
    all_appendices['Input Data Analysis'] = get_input_data_appendix_content(params, appendix_plot_buffers, styles, data)

    # Strategy Evaluations appendix
    # --- Strategy Evaluations Appendix (Converted from Markdown) ---
    try:
        from reporting.content import get_strategy_evaluations_content
        eval_content = get_strategy_evaluations_content()
        
        def _md_to_xml(text):
            """Converts basic Markdown to ReportLab-compatible XML."""
            import re
            # Headers (#### Header) -> Bold + Break
            text = re.sub(r'#{3,4}\s*(.*?)(\n|$)', r'<b>\1</b><br/>', text)
            # Bold (**text**) -> <b>text</b>
            text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
            # Lists (* Item) -> Bullet
            text = re.sub(r'^\s*\*\s+(.*)', r'&bull; \1', text, flags=re.MULTILINE)
            # Newlines -> <br/>
            text = text.replace('\n', '<br/>')
            return text

        strategy_eval_content = []
        strategy_eval_content.append(Paragraph(_md_to_xml(eval_content['intro']), styles['Justify']))
        strategy_eval_content.append(Spacer(1, 12))
        strategy_eval_content.append(Paragraph(_md_to_xml(eval_content['process']), styles['Justify']))
        strategy_eval_content.append(Spacer(1, 12))
        strategy_eval_content.append(Paragraph(_md_to_xml(eval_content['scenarios']), styles['Justify']))
        strategy_eval_content.append(Spacer(1, 12))
        strategy_eval_content.append(Paragraph(_md_to_xml(eval_content['metrics']), styles['Justify']))
        strategy_eval_content.append(Spacer(1, 12))
        strategy_eval_content.append(Paragraph(_md_to_xml(eval_content['wisdom']), styles['Justify']))
        all_appendices['Strategy Evaluations'] = strategy_eval_content
    except Exception as e:
        logging.warning(f"Could not generate Strategy Evaluations appendix for PDF: {e}")
    
    all_appendices['Glossary'] = glossary_content
    if params.get('show_ai_prompt', False):
        all_appendices['AI Prompt'] = [Paragraph(p, styles['Code']) for p in gemini_prompt_text.split('\n')]

    # --- Build the appendices by iterating through the authoritative order ---
    for i, appendix_title in enumerate(APPENDIX_ORDER):
        if appendix_title in all_appendices and all_appendices[appendix_title]:
            chapter_count += 1
            key = f"chap{chapter_count}"
            p = Paragraph(f'<a name="{key}"/>Appendix {i+1}: {appendix_title}', styles['H2'])
            p.toc_key = key
            story.append(p)
            story.extend(all_appendices[appendix_title])
            story.append(PageBreak())

    doc.multiBuild(story, onFirstPage=on_page, onLaterPages=on_page)

    if to_buffer:
        logging.info("PDF report generated into in-memory buffer.")
        buffer.seek(0)
        return buffer
    else:
        logging.info(f"PDF report saved as '{filename}'")
        absolute_path = os.path.abspath(filename)
        return absolute_path
