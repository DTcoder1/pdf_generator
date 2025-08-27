# pip install reportlab

import os
from typing import List, Dict, Any

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# =========================
# Typography / Layout Utils (Unchanged)
# =========================

def register_fonts(font_path="fonts", font_files=("Poppins-Bold.ttf", "Poppins-Regular.ttf")):
    os.makedirs(font_path, exist_ok=True)
    registered_fonts = {"bold": "Helvetica-Bold", "regular": "Helvetica"}
    for font_file, family_name in zip(font_files, ["bold", "regular"]):
        font_name = os.path.splitext(font_file)[0]
        full_path = os.path.join(font_path, font_file)
        if os.path.exists(full_path):
            pdfmetrics.registerFont(TTFont(font_name, full_path))
            registered_fonts[family_name] = font_name
    return registered_fonts

def string_width(text: str, font_name: str, font_size: float) -> float:
    return pdfmetrics.stringWidth(str(text), font_name, font_size)

def wrap_text_to_width(text: str, font_name: str, font_size: float, max_width: float) -> List[str]:
    lines, words = [], str(text).split()
    if not words: return [""]
    current_line = words[0]
    for word in words[1:]:
        if string_width(f"{current_line} {word}", font_name, font_size) <= max_width:
            current_line += f" {word}"
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    return lines

# ============================
# Table Drawing Logic with Caption
# ============================

def draw_rounded_table(c: canvas.Canvas, x: float, y: float, config: Dict[str, Any], fonts: Dict[str, Any]):
    """
    Draws a fully-rounded table and adds a caption below it.
    """
    # --- 1. Configuration and Style Extraction ---
    data = config.get("data", [])
    column_styles = config.get("column_styles", {})
    table_width = config.get("width", A4[0] - 2 * inch)
    
    header_style = config.get("header_style", {})
    header_font = fonts.get(header_style.get("font", "bold"), fonts["bold"])
    header_font_size = header_style.get("font_size", 11)
    header_fill = header_style.get("fill_color", colors.HexColor("#163b8a"))
    header_text_color = header_style.get("text_color", colors.white)
    header_padding = header_style.get("padding", 8)
    header_height = header_font_size + 2 * header_padding

    cell_padding = config.get("cell_padding", 6)
    line_spacing = 1.2
    table_radius = config.get("radius", 8)
    
    border_color = colors.HexColor("#E5E7EB")
    alt_row_color = colors.HexColor("#F3F4F6")
    default_text_color = colors.HexColor("#111827")
    
    # --- 2. Pre-calculate Total Table Height ---
    total_row_height = 0
    row_heights = []
    for row_data in data:
        max_lines = 1
        for key, style in column_styles.items():
            font = fonts.get(style.get("font", "regular"), fonts["regular"])
            font_size = style.get("font_size", 10)
            col_width = style["width"] - (2 * cell_padding)
            lines = wrap_text_to_width(str(row_data.get(key, "")), font, font_size, col_width)
            max_lines = max(max_lines, len(lines))
        row_h = max_lines * (font_size * line_spacing) + (2 * cell_padding)
        row_heights.append(row_h)
        total_row_height += row_h
    total_table_height = header_height + total_row_height
    
    # --- 3. Draw the Table using a Clipping Path ---
    c.saveState()
    path = c.beginPath()
    path.roundRect(x, y - total_table_height, table_width, total_table_height, table_radius)
    c.clipPath(path, stroke=0, fill=0)
    
    c.setFillColor(colors.white)
    c.rect(x, y - total_table_height, table_width, total_table_height, stroke=0, fill=1)
    c.setStrokeColor(border_color)
    c.roundRect(x, y - total_table_height, table_width, total_table_height, table_radius, stroke=1, fill=0)

    # Draw Header
    current_y = y
    c.setFillColor(header_fill)
    c.rect(x, current_y - header_height, table_width, header_height, stroke=0, fill=1)
    current_x = x
    for key, style in column_styles.items():
        c.setFillColor(header_text_color)
        c.setFont(header_font, header_font_size)
        header_text = style.get("header", key.capitalize())
        text_w = string_width(header_text, header_font, header_font_size)
        text_y = current_y - header_height/2 - header_font_size/2
        text_x = current_x + (style["width"] / 2) - (text_w / 2)
        c.drawString(text_x, text_y, header_text)
        current_x += style["width"]
    current_y -= header_height
    
    # Draw Rows
    for i, row_data in enumerate(data):
        row_h = row_heights[i]
        if i % 2 == 1:
            c.setFillColor(alt_row_color)
            c.rect(x, current_y - row_h, table_width, row_h, stroke=0, fill=1)
        current_x = x
        for key, style in column_styles.items():
            font = fonts.get(style.get("font", "regular"), fonts["regular"])
            font_size = style.get("font_size", 10)
            text_color = style.get("text_color", default_text_color)
            align = style.get("align", "LEFT").upper()
            c.setFont(font, font_size)
            c.setFillColor(text_color)
            lines = wrap_text_to_width(str(row_data.get(key, "")), font, font_size, style["width"] - 2 * cell_padding)
            line_y = current_y - cell_padding - font_size
            for line in lines:
                if align == "RIGHT": line_x = current_x + style["width"] - cell_padding - string_width(line, font, font_size)
                elif align == "CENTER": line_x = current_x + style["width"]/2 - string_width(line, font, font_size)/2
                else: line_x = current_x + cell_padding
                c.drawString(line_x, line_y, line)
                line_y -= font_size * line_spacing
            current_x += style["width"]
        c.setStrokeColor(border_color)
        c.line(x, current_y - row_h, x + table_width, current_y - row_h)
        current_y -= row_h
    c.restoreState() # Clipping path is now removed

    # --- 4. Draw the Caption Below the Table ---
    caption = config.get("caption")
    if caption:
        style = config.get("caption_style", {})
        font = fonts.get(style.get("font", "regular"), fonts["regular"])
        font_size = style.get("font_size", 9)
        color = style.get("text_color", colors.HexColor("#6B7280"))
        align = style.get("align", "LEFT").upper()
        
        padding = 12
        caption_y = y - total_table_height - padding
        lines = wrap_text_to_width(caption, font, font_size, table_width)
        
        c.setFont(font, font_size)
        c.setFillColor(color)
        for line in lines:
            if align == "RIGHT": caption_x = x + table_width - string_width(line, font, font_size)
            elif align == "CENTER": caption_x = x + table_width/2 - string_width(line, font, font_size)/2
            else: caption_x = x
            c.drawString(caption_x, caption_y, line)
            caption_y -= font_size * 1.2

# ====================
# Main PDF Builder
# ====================

def create_pdf_with_table(output_filename: str, table_config: Dict[str, Any]):
    PAGE_WIDTH, PAGE_HEIGHT = A4
    c = canvas.Canvas(output_filename, pagesize=A4)
    fonts = register_fonts()
    
    c.setFont(fonts["bold"], 24)
    c.setFillColor(colors.HexColor("#111827"))
    c.drawString(0.5 * inch, PAGE_HEIGHT - 1 * inch, "Product Inventory Report")
    
    start_x = 0.5 * inch
    start_y = PAGE_HEIGHT - 1.5 * inch
    
    draw_rounded_table(c, start_x, start_y, table_config, fonts)
    
    c.save()
    print(f"✅ Successfully created PDF: {output_filename}")

# ========================
# Demo Data and Execution
# ========================

if __name__ == "__main__":
    
    dummy_data = [
        {'id': 'SKU-001', 'name': 'Quantum Hyper-Sprocket', 'stock': 25, 'price': 149.99},
        {'id': 'SKU-002', 'name': 'Flex-Grip Armature (Model X)', 'stock': 150, 'price': 89.50},
        {'id': 'SKU-003', 'name': 'A long product name that will definitely need to wrap to the next line to fit', 'stock': 0, 'price': 499.00},
        {'id': 'SKU-004', 'name': 'Micro-Fiber Polishing Cloth', 'stock': 1200, 'price': 5.25},
        {'id': 'SKU-005', 'name': 'Data Crystal (2TB)', 'stock': 55, 'price': 215.75},
    ]

    total_table_width = A4[0] - 1 * inch
    
    my_table_config = {
        "data": dummy_data,
        "width": total_table_width,
        "radius": 8,
        
        # --- NEW: Caption Configuration ---
        "caption": "Table 1: A detailed overview of product inventory as of August 2025. This data is illustrative and subject to real-time changes.",
        "caption_style": {
            "font": "regular",
            "font_size": 9,
            "text_color": colors.HexColor("#6B7280"), # --neutral-medium
            "align": "LEFT",
        },
        
        "header_style": {
            "font": "bold",
            "font_size": 11,
            "fill_color": colors.HexColor("#163b8a"),
            "text_color": colors.white,
        },
        "column_styles": {
            "id": {"header": "Product ID", "width": total_table_width * 0.15, "align": "LEFT", "font": "bold", "text_color": colors.HexColor("#374151")},
            "name": {"header": "Product Name", "width": total_table_width * 0.45, "align": "LEFT"},
            "stock": {"header": "In Stock", "width": total_table_width * 0.15, "align": "CENTER", "text_color": colors.HexColor("#EF4444")},
            "price": {"header": "Unit Price ($)", "width": total_table_width * 0.25, "align": "RIGHT", "font_size": 11},
        }
    }

    create_pdf_with_table("final_table_with_caption.pdf", my_table_config)