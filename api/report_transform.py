from reporting.content import get_section_intro, get_glossary_data
from core.shared_logic import get_info_boxes_text

def transform_report_data_to_ui_list(report_data: dict) -> list:
    """
    Transforms the final report_data dictionary from the simulation engine
    into a list of dictionaries, where each dictionary represents a UI component
    that can be rendered by `render_live_results`.

    This acts as an adapter between the decoupled engine and the UI rendering logic.
    """
    ui_list = []
    sim_params = report_data.get('settings', {}).get('flat_params', {})
    final_stats = report_data.get('final_stats', {})

    # --- Executive Summary ---
    gemini_analysis = report_data.get('gemini_analysis', {})
    gemini_main_outcome = gemini_analysis.get('main_outcome', "AI analysis was not available.")
    gemini_bottom_line = gemini_analysis.get('bottom_line', "AI analysis was not available.")

    from core.simulation_currency import get_simulation_currency
    from core.currency_config import format_currency_amount
    
    # Extract currency from simulation parameters
    currency = get_simulation_currency(sim_params)
    
    ui_list.append({'type': 'intro', 'data': get_section_intro("Executive Summary"), 'section': 'Executive Summary'})
    initial_formatted = format_currency_amount(sim_params.get('initial_investment', 0), currency, decimals=0)
    scenario_text = f"This report analyzes a \"{' '.join(word.capitalize() for word in sim_params.get('strategy', '').split('_'))}\" strategy using {sim_params.get('asset_name', 'the selected asset')}, starting with {initial_formatted} over {sim_params.get('num_years', 0)} years."
    ui_list.append({'type': 'text', 'data': f"<b>The Scenario:</b> {scenario_text}", 'section': 'Executive Summary'})
    ui_list.append({'type': 'text', 'data': f"<b>The Main Outcome:</b> {gemini_main_outcome}", 'section': 'Executive Summary'})
    median_formatted = format_currency_amount(int(final_stats.get('median_final_net_worth', 0)), currency, decimals=0)
    mean_formatted = format_currency_amount(int(final_stats.get('mean_final_net_worth', 0)), currency, decimals=0)
    stats_text = f"""
<b>Final Net Worth (Median | Mean):</b> {median_formatted} | {mean_formatted}<br/>
<b>Chance of Profit:</b> {final_stats.get('chance_of_profit', 0.0):.1%}<br/>
<b>Risk of Insolvency/Depletion:</b> {final_stats.get('chance_of_ruin', 0.0):.1%}<br/>
"""
    ui_list.append({'type': 'text', 'data': f"<b>Key Statistics:</b><br>{stats_text}", 'section': 'Executive Summary'})
    ui_list.append({'type': 'text', 'data': f"<b>The Bottom Line:</b> {gemini_bottom_line}", 'section': 'Executive Summary'})

    # --- Simulation Settings ---
    ui_list.append({'type': 'intro', 'data': get_section_intro("Simulation Settings"), 'section': 'Simulation Settings'})
    ui_list.append({'type': 'settings_table', 'data': report_data.get('settings', {}).get('structured'), 'section': 'Simulation Settings'})

    # --- Input Data Analysis ---
    ui_list.append({'type': 'intro', 'data': get_section_intro("Input Data Analysis"), 'section': 'Input Data Analysis'})
    for plot in report_data.get('input_plots', []):
        plot['section'] = 'Input Data Analysis'
        ui_list.append(plot)

    # --- Simulation Summary ---
    ui_list.append({'type': 'intro', 'data': get_section_intro("Simulation Summary"), 'section': 'Simulation Summary'})
    
    # --- Format structured data into HTML for the UI ---
    structured_info = get_info_boxes_text(sim_params, final_stats)
    outcome_html = f"<b>--- Outcome Analysis (Yr {sim_params.get('num_years', 'N/A')}) ---</b><br/>" + "<br/>".join([f"{item['label']}: {item['value']}" for item in structured_info['outcome']])
    risk_html = "<b>--- Risk Analysis ---</b><br/>" + "<br/>".join([f"{item['label']}: {item['value']}" for item in structured_info['risk']])
    
    # Add psychological stress indicators if available
    if 'psychological' in structured_info:
        psych_html = "<b>--- Psychological Stress Indicators ---</b><br/>" + "<br/>".join([f"{item['label']}: {item['value']}" for item in structured_info['psychological']])
        ui_list.append({'type': 'info_box', 'data': psych_html, 'caption': 'How stressful is this strategy to follow?', 'section': 'Simulation Summary'})
    
    ui_list.append({'type': 'info_box', 'data': outcome_html, 'section': 'Simulation Summary'})
    ui_list.append({'type': 'info_box', 'data': risk_html, 'section': 'Simulation Summary'})



    # Advanced Stats Summary Box
    adv_stats_summary = (f"<b>Asset Sharpe Ratio:</b> {final_stats.get('asset_sharpe_ratio', 0.0):.2f}<br/>"
                         f"<b>Asset Sortino Ratio:</b> {final_stats.get('asset_sortino_ratio', 0.0):.2f}<br/>"
                         f"<b>Strategy Sharpe Ratio:</b> {final_stats.get('strategy_sharpe_ratio', 0.0):.2f}<br/>"
                         f"<b>Strategy Sortino Ratio:</b> {final_stats.get('strategy_sortino_ratio', 0.0):.2f}<br/>"
                         f"<b>Asset Ulcer Index:</b> {final_stats.get('asset_ulcer_index', 0.0):.2f}<br/>"
                         f"<b>Strategy Ulcer Index (Median):</b> {final_stats.get('median_strategy_ulcer_index', 0.0):.2f}")
    ui_list.append({'type': 'info_box', 'data': adv_stats_summary, 'caption': "Advanced Statistics Summary (see appendix for details)", 'section': 'Simulation Summary'})

    # Output Plots
    for plot in report_data.get('output_plots', []):
        plot['section'] = 'Simulation Summary'
        ui_list.append(plot)

    # --- Qualitative Analysis ---
    if 'full_analysis' in gemini_analysis:
        ui_list.append({'type': 'intro', 'data': get_section_intro("Qualitative Analysis"), 'section': 'Qualitative Analysis'})
        ui_list.append({'type': 'text', 'data': gemini_analysis['full_analysis'], 'caption': 'Full Analysis', 'section': 'Qualitative Analysis'})

    # --- Appendices ---
    # AI Prompt
    if 'prompt' in gemini_analysis:
        ui_list.append({'type': 'text', 'data': f"```\n{gemini_analysis['prompt']}\n```", 'section': 'Appendices', 'sub_section': 'AI Prompt'})

    # Advanced Stats Appendix
    from reporting.content import get_structured_advanced_stats
    ui_list.append({'type': 'intro', 'data': get_section_intro("Advanced Statistics Appendix"), 'section': 'Appendices', 'sub_section': 'Advanced Statistics'})
    structured_adv_stats = get_structured_advanced_stats(final_stats, sim_params)
    ui_list.append({'type': 'advanced_stats_table', 'data': structured_adv_stats, 'section': 'Appendices', 'sub_section': 'Advanced Statistics'})

    # Glossary
    glossary_data = get_glossary_data()
    glossary_md_parts = []
    for group_title, terms in glossary_data.items():
        glossary_md_parts.append(f"**{group_title}**")
        for term, definition in sorted(terms.items()):
            glossary_md_parts.append(f"**{term}**<br>{definition}")
    glossary_md = "<br><br>".join(glossary_md_parts)
    ui_list.append({'type': 'text', 'data': glossary_md, 'section': 'Appendices', 'sub_section': 'Glossary'})

    return ui_list