"""
PDF Manifest Renderer - Helper functions for manifest-driven PDF generation
"""

from reportlab.platypus import Paragraph, Spacer, Table, Image, PageBreak
from reportlab.lib.units import inch
from reporting.content import REPORT_STRUCTURE, get_section_intro, get_disclaimer_text
from reporting.content import get_glossary_data, get_methodology_intro, get_methodology_detailed
from reporting.pdf_tables import create_styled_info_table
import logging


def render_item_for_pdf(item, context, story, styles):
    """
    Render a single item for PDF based on its type.
    
    Args:
        item: Item dict from REPORT_STRUCTURE
        context: Data context with all content
        story: ReportLab story list to append to
        styles: ReportLab styles dict
    """
    item_type = item.get('type')
    key = item.get('key')
    optional = item.get('optional', False)
    
    # Skip optional items if not in context
    if optional and key not in context:
        return
    
    try:
        if item_type == 'text_block':
            # Handle text blocks (disclaimer, AI analysis, etc.)
            if key in context and context[key]:
                text = context[key]
                story.append(Paragraph(text, styles['Justify']))
                story.append(Spacer(1, 0.15 * inch))
                
        elif item_type == 'intro':
            # Section intro text
            section_name = context.get('_section_name', '')
            intro_text = get_section_intro(section_name.replace('Appendices: ', ''))
            if intro_text:
                story.append(Paragraph(intro_text, styles['Justify']))
                story.append(Spacer(1, 0.15 * inch))
                
        elif item_type == 'table':
            # Handle tables (settings, stats, etc.)
            if key in context and context[key]:
                # Special handling for settings_table which has sections
                if key == 'settings_table':
                    # settings_table has structure: [{'title': 'Section', 'metrics': [{label, value}, ...]}, ...]
                    for section in context[key]:
                        section_title = section.get('title', '')
                        section_metrics = section.get('metrics', [])
                        if section_metrics:
                            table = create_styled_info_table(section_metrics, section_title)
                            story.append(table)
                            story.append(Spacer(1, 0.15 * inch))
                else:
                    # Regular flat table
                    table = create_styled_info_table(context[key], key)
                    story.append(table)
                    story.append(Spacer(1, 0.15 * inch))
                
        elif item_type == 'ai_analysis':
            # AI-generated analysis text
            if key in context and context[key]:
                # Split by paragraphs and render each
                text = context[key]
                for paragraph in text.split('\n'):
                    if paragraph.strip():
                        story.append(Paragraph(paragraph, styles['Justify']))
                story.append(Spacer(1, 0.15 * inch))
                
        elif item_type == 'glossary':
            # Special handling for glossary
            glossary_data = get_glossary_data()
            for group_title, terms in glossary_data.items():
                story.append(Paragraph(group_title, styles['H3']))
                story.append(Spacer(1, 6))
                for term, definition in sorted(terms.items()):
                    story.append(Paragraph(f"<b>{term}</b>", styles['Normal']))
                    story.append(Paragraph(definition, styles['Justify']))
                    story.append(Spacer(1, 6))
                story.append(Spacer(1, 12))
                
    except Exception as e:
        logging.error(f"Error rendering PDF item {item_type}:{key} - {e}")


def render_section_for_pdf(section_name, items, context, story, styles):
    """
    Render a complete section for PDF based on manifest structure.
    
    Args:
        section_name: Name of the section
        items: List of item dicts from REPORT_STRUCTURE
        context: Data context with all content
        story: ReportLab story list to append to
        styles: ReportLab styles dict
    """
    # Add section name to context for intro rendering
    context['_section_name'] = section_name
    
    # Render each item in the section
    for item in items:
        render_item_for_pdf(item, context, story, styles)

