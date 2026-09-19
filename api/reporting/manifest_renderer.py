"""
Manifest-based report rendering functions.
These functions consume the REPORT_STRUCTURE manifest to generate reports.
"""

import logging
from reporting.content import REPORT_STRUCTURE, get_section_intro
from reporting.components import thousands_scaling_caption


def render_item_for_ui(item, context, send_result, section_name):
    """
    Render a single manifest item for UI display.
    
    Args:
        item: Dict with 'type' and 'key'
        context: Data context dict
        send_result: Callable to send results to UI
        section_name: Name of current section
    """
    item_type = item.get('type')
    key = item.get('key')
    optional = item.get('optional', False)
    
    # Handle optional items
    if optional and key not in context:
        return
    
    try:
        if item_type == 'text_block':
            if key == 'disclaimer':
                send_result('text', context['disclaimer'], section='Important Disclaimer')
            elif key == 'methodology_flowchart_description':
                send_result('text', f"<b>Simulation Process Flow</b><br/><br/>{context['methodology_flowchart_desc']}", 
                           section=section_name, sub_section='Introduction')
            elif key == 'methodology_detailed':
                send_result('text', context['methodology_detailed'], 
                           section=section_name, sub_section='Detailed Description')
            elif key == 'strategy_description':
                send_result('text', context['strategy_description'], section=section_name)
            elif key.startswith('strategy_eval_'):
                if context.get('strategy_eval_content'):
                    eval_key = key.replace('strategy_eval_', '')
                    send_result('text', context['strategy_eval_content'][eval_key], 
                               section='Appendices', sub_section='Strategy Evaluations')
            elif key == 'ai_prompt_text':
                # AI prompt handled specially
                pass  # Implement if needed
                
        elif item_type == 'intro':
            intro_text = get_section_intro(section_name.replace('Appendices: ', ''))
            if section_name.startswith('Appendices:'):
                sub_section = section_name.replace('Appendices: ', '')
                send_result('intro', intro_text, section='Appendices', sub_section=sub_section)
            else:
                send_result('intro', intro_text, section=section_name)
                
        elif item_type == 'table':
            if key == 'transaction_types':
                send_result('key_value_table', context['transaction_types'], 
                           caption='Available Transaction Types', section=section_name)
            elif key == 'settings_table':
                send_result('settings_table', context['settings_table'], section=section_name)
            elif key == 'asset_info' and context.get('asset_info'):
                send_result('key_value_table', context['asset_info'], 
                           caption='Asset Information', section=section_name)
            elif key == 'key_stats':
                send_result('key_stats_table', context['summary_content']['key_stats'], 
                           caption='Key Statistics', section=section_name)
            elif key == 'advanced_stats':
                send_result('advanced_stats_table', context['advanced_stats'], 
                           section='Appendices', sub_section='Advanced Statistics')
                           
        elif item_type == 'info_box':
            info_boxes = context['info_boxes']
            if key in info_boxes:
                caption_map = {
                    'outcome_analysis': f"Outcome Analysis (Yr {context['params'].get('num_years', 'N/A')})",
                    'risk_analysis': "Risk Analysis",
                    'psychological_metrics': "Psychological Stress Indicators",
                    'advanced_stats_summary': "Advanced Statistics Summary (see appendix for details)"
                }
                send_result('key_value_table', info_boxes[key], 
                           caption=caption_map.get(key, key), section=section_name)
                           
        elif item_type == 'ai_analysis':
            if key == 'gemini_scenario':
                send_result('text', f"<b>The Scenario:</b> {context['summary_content']['scenario']}", 
                           section=section_name)
            elif key == 'gemini_main_outcome':
                send_result('text', f"<b>The Main Outcome:</b> {context['summary_content']['main_outcome']}", 
                           section=section_name)
            elif key == 'gemini_bottom_line':
                send_result('text', f"<b>The Bottom Line:</b> {context['summary_content']['bottom_line']}", 
                           section=section_name)
            elif key == 'gemini_full_analysis':
                analysis_text = context.get('gemini_analysis', '')
                logging.info(f"Rendering gemini_full_analysis: text length = {len(analysis_text) if analysis_text else 0}")
                logging.info(f"Rendering gemini_full_analysis: text preview = {analysis_text[:200] if analysis_text else 'EMPTY'}")
                send_result('text', analysis_text, 
                           caption='Full Analysis', section=section_name)
                           
        elif item_type == 'dataframe':
            if key == 'average_results' and context.get('average_results') is not None:
                df_for_ui = context['average_results'].to_json(orient='split')
                send_result('dataframe', df_for_ui,
                           caption=thousands_scaling_caption(context['currency'], ", representing the average state of the portfolio at the end of each year, after all transactions have been completed. NOTE: Average results are heavily affected by outliers, look at median table to understand typical outcomes."),
                           section='Appendices', sub_section='Average Yearly Results')
            elif key == 'median_results' and context.get('median_results') is not None:
                df_for_ui = context['median_results'].to_json(orient='split')
                send_result('dataframe', df_for_ui,
                           caption=thousands_scaling_caption(context['currency'], ", representing the median state of the portfolio at the end of each year, after all transactions have been completed."),
                           section='Appendices', sub_section='Median Yearly Results')
            elif key == 'example_path' and context.get('example_path') is not None:
                caption = context.get('caption') or thousands_scaling_caption(context['currency'], "...")
                send_result('dataframe', context['example_path'].to_json(orient='split'),
                           caption=caption,
                           section='Appendices', sub_section='Example Simulation Path')
                           
        elif item_type == 'glossary':
            send_result('glossary', context['glossary'], 
                       section='Appendices', sub_section='Glossary')
                       
        elif item_type == 'flowchart':
            # Flowcharts handled separately (need file paths)
            pass
            
        elif item_type == 'plot':
            # Plots handled separately (need generation)
            pass
            
        elif item_type == 'evaluation':
            # Strategy evaluation handled separately (complex rendering)
            pass
            
    except Exception as e:
        logging.error(f"Error rendering item {item_type}:{key} - {e}")


def render_section_for_ui(section_name, items, context, send_result):
    """
    Render all items in a section for UI display.
    
    Args:
        section_name: Name of the section
        items: List of item dicts from manifest
        context: Data context
        send_result: Callable to send results
    """
    for item in items:
        render_item_for_ui(item, context, send_result, section_name)
