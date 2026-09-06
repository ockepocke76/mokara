"""
Generalized PDF table styling functions.
Provides consistent, professional table formatting for all PDF reports.
"""

import logging
from reportlab.lib.units import inch
from reportlab.platypus import Table, TableStyle, Spacer, Paragraph
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet

# Professional color scheme
DARK_BLUE = colors.HexColor('#003366')


def create_styled_info_table(data, title):
    """
    Generalized helper function to create a styled two-column info table.
    
    Features:
    - White text on dark blue header
    - Bold left column (labels), normal right column (values)
    - Automatic text wrapping
    - Professional grid and padding
    
    Args:
        data: Either a list of 2-element lists/tuples [(label, value), ...]
              or a list of dicts with 'label' and 'value' keys
        title: The table title (displayed in header with white text on blue background)
    
    Returns:
        Table object with professional styling, or Spacer if data is invalid
    """
    styles = getSampleStyleSheet()
    
    # Validate data
    if not data:
        logging.warning(f"Attempted to create table '{title}' with empty data")
        return Spacer(1, 0)
    
    if not isinstance(data, list):
        logging.error(f"Data for '{title}' is not a list: {type(data)}")
        return Spacer(1, 0)
    
    # Convert data to standardized format
    table_rows = []
    for i, item in enumerate(data):
        # Handle dict format (from components)
        if isinstance(item, dict):
            label = str(item.get('label', ''))
            value = str(item.get('value', ''))
        # Handle tuple/list format (from direct calls)
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            label = str(item[0])
            value = str(item[1])
        else:
            logging.warning(f"Row {i} in '{title}' has invalid format: {item}")
            continue
        
        if label or value:
            # Wrap in Paragraphs for proper text wrapping
            # Use <b> tag for first column to make it bold
            # Apply conditional red formatting for negative values
            if value.strip().startswith('-') or (value.strip().startswith('-$') or value.strip().startswith('-SEK')):
                # Use a specific red color (Tailwind red-500 equivalent)
                value = f'<font color="#ef4444">{value}</font>'
                
            label_para = Paragraph(f'<b>{label}</b>', styles['Normal'])
            value_para = Paragraph(value, styles['Normal'])
            table_rows.append([label_para, value_para])
    
    if not table_rows:
        logging.warning(f"No valid rows for table '{title}'")
        return Spacer(1, 0)
    
    # Add title header row with white text
    title_para = Paragraph(f'<b><font color="white">{title}</font></b>', styles['Normal'])
    table_data = [[title_para, ""]] + table_rows
    

    
    # Create table with professional styling
    table = Table(table_data, colWidths=[3.0 * inch, 2.8 * inch])
    style = TableStyle([
        ('SPAN', (0, 0), (1, 0)),  # Span title across both columns
        ('BACKGROUND', (0, 0), (1, 0), DARK_BLUE),  # Blue header background
        ('TEXTCOLOR', (0, 0), (1, 0), colors.whitesmoke),  # White header text
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),  # Left align all cells
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),  # Top align for multi-line cells
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),  # Bold left column (labels)
        ('FONTNAME', (1, 1), (1, -1), 'Helvetica'),  # Normal right column (values)
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),  # Light grid lines
    ])
    table.setStyle(style)
    return table
