# pip install reportlab pillow

import os
from typing import Literal, Tuple, List, Dict, Any

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Pillow only used to generate a placeholder image if none exists
from PIL import Image, ImageDraw, ImageFont

# =========================
# Typography / Layout utils
# =========================

def string_width(text: str, font_name: str, font_size: float) -> float:
    """Calculates the width of a string."""
    return pdfmetrics.stringWidth(text, font_name, font_size)

def wrap_text_to_width(text: str, font_name: str, font_size: float, max_width: float) -> List[str]:
    """Greedy word wrap based on stringWidth."""
    words = text.split()
    if not words:
        return []
    lines, line = [], words[0]
    for w in words[1:]:
        test = f"{line} {w}"
        if string_width(test, font_name, font_size) <= max_width:
            line = test
        else:
            lines.append(line)
            line = w
    lines.append(line)
    return lines

def auto_fit_font_size(text: str, font_name: str, max_width: float, max_size: float, min_size: float) -> float:
    """Find a font size that makes one line of text fit max_width (descending)."""
    size = max_size
    while size >= min_size:
        if string_width(text, font_name, size) <= max_width:
            return size
        size -= 1
    return min_size

def draw_rounded_panel(c, x, y, w, h, *, radius=5, fill_hex="#000000", alpha=0.40, stroke=0):
    """Semi-opaque rounded rectangle to sit behind text."""
    col = colors.HexColor(fill_hex)
    c.setFillColor(colors.Color(col.red, col.green, col.blue, alpha=alpha))
    c.roundRect(x, y, w, h, radius, stroke=stroke, fill=1)

# ========================
# WIDGET DRAWING FUNCTIONS
# ========================

def draw_rectangular_widget(c, x, y, w, h, content: Dict[str, Any], fonts: Dict[str, str]):
    """
    Draws a rectangular widget with a title, body text, sources, and a severity flag.
    """
    padding = 0.5 * inch
    severity = content.get("severity", "grey")
    
    severity_colors = {
        "red": "#FF5A5F",
        "yellow": "#FFB400",
        "grey": "#B0B0B0"
    }
    
    # Main Panel
    draw_rounded_panel(c, x, y, w, h, radius=8, fill_hex="#1E1E24", alpha=0.85)
    
    # Severity Flag Bar
    flag_color = colors.HexColor(severity_colors.get(severity, "#B0B0B0"))
    c.setFillColor(flag_color)
    c.rect(x, y, 10, h, stroke=0, fill=1)

    inner_x = x + padding
    inner_w = w - 2 * padding

    # Title
    c.setFillColor(colors.white)
    title = content.get("title", "No Title")
    title_size = 18
    c.setFont(fonts["bold"], title_size)
    c.drawString(inner_x, y + h - padding + 10, title)

    # Body Text
    c.setFillColor(colors.lightgrey)
    body_text = content.get("text", "")
    body_size = 11
    c.setFont(fonts["regular"], body_size)
    text_lines = wrap_text_to_width(body_text, fonts["regular"], body_size, inner_w)
    
    text_y = y + h - padding - title_size
    for line in text_lines:
        c.drawString(inner_x, text_y, line)
        text_y -= body_size * 1.4

    # Clickable Sources as Buttons
    sources = content.get("sources", [])
    source_size = 9
    c.setFont(fonts["light"], source_size)
    
    source_x = x + padding
    source_y = y + padding - 10
    
    for source in sources:
        label = source.get("label", "Source")
        link_id = source.get("id", "")
        
        btn_w = string_width(label, fonts["light"], source_size) + 20
        btn_h = source_size + 8
        
        # Draw button background
        draw_rounded_panel(c, source_x, source_y, btn_w, btn_h, radius=5, fill_hex="#333338", alpha=1)
        
        # Draw button text
        c.setFillColor(colors.white)
        c.drawString(source_x + 10, source_y + 4, label)
        
        # Create clickable link area
        c.linkRect(label, link_id, (source_x, source_y, source_x + btn_w, source_y + btn_h), relative=1)
        
        source_x += btn_w + 10


def draw_square_widget(c, x, y, size, content: Dict[str, Any], fonts: Dict[str, str]):
    """
    Draws a square widget with block text.
    """
    padding = 0.2 * inch
    inner_size = size - 2 * padding
    
    draw_rounded_panel(c, x, y, size, size, radius=8, fill_hex="#1E1E24", alpha=0.85)
    
    c.setFillColor(colors.white)
    
    text = content.get("text", "")
    font_size = content.get("font_size", 12)
    c.setFont(fonts["regular"], font_size)
    
    lines = wrap_text_to_width(text, fonts["regular"], font_size, inner_size)
    
    text_y = y + size / 2 + (len(lines) * font_size * 1.2) / 2 - font_size
    for line in lines:
        c.drawCentredString(x + size / 2, text_y, line)
        text_y -= font_size * 1.2

# ====================
# Background image util
# ====================

def draw_cover_image(
    c,
    image_path: str,
    page_size: Tuple[float, float],
    *,
    darken: float = 0.0,
):
    """
    Draw an image to cover the full page.
    """
    width, height = page_size

    if not os.path.exists(image_path):
        c.setFillColor(colors.HexColor("#1c1c1e"))
        c.rect(0, 0, width, height, stroke=0, fill=1)
        return

    img = ImageReader(image_path)
    img_w, img_h = img.getSize()
    img_aspect = img_h / float(img_w)

    draw_h = height
    draw_w = draw_h / img_aspect
    if draw_w < width:
        draw_w = width
        draw_h = draw_w * img_aspect

    x = (width - draw_w) / 2.0
    y = (height - draw_h) / 2.0

    c.drawImage(img, x, y, width=draw_w, height=draw_h, mask='auto')

    if darken > 0:
        darken = max(0.0, min(1.0, darken))
        c.setFillColor(colors.Color(0, 0, 0, alpha=darken))
        c.rect(0, 0, width, height, stroke=0, fill=1)

# ===========
# Main builder
# ===========

def create_pdf_layout(
    output_filename="widgets_layout.pdf",
    *,
    page_size=A4,
    background_image_path="assets/banner-2.jpg",
    fonts_path="assets/fonts",
    font_files=("Poppins-Bold.ttf", "Poppins-Light.ttf", "Poppins-Regular.ttf"),
    widgets: List[Dict[str, Any]]
):
    """
    Builds the PDF with a flexible widget layout and a sources page.
    """
    # ========== Fonts ==========
    bold_file, light_file, regular_file = font_files
    font_bold_name = "Helvetica-Bold"
    if os.path.exists(os.path.join(fonts_path, bold_file)):
        pdfmetrics.registerFont(TTFont("Poppins-Bold", os.path.join(fonts_path, bold_file)))
        font_bold_name = "Poppins-Bold"
    
    font_light_name = "Helvetica"
    if os.path.exists(os.path.join(fonts_path, light_file)):
        pdfmetrics.registerFont(TTFont("Poppins-Light", os.path.join(fonts_path, light_file)))
        font_light_name = "Poppins-Light"

    font_regular_name = "Helvetica"
    if os.path.exists(os.path.join(fonts_path, regular_file)):
        pdfmetrics.registerFont(TTFont("Poppins-Regular", os.path.join(fonts_path, regular_file)))
        font_regular_name = "Poppins-Regular"

    fonts = {
        "bold": font_bold_name,
        "light": font_light_name,
        "regular": font_regular_name,
    }

    c = canvas.Canvas(output_filename, pagesize=page_size)
    width, height = page_size

    # ========== Page 1: Widgets ==========
    draw_cover_image(c, background_image_path, (width, height), darken=0.6)

    all_sources = []
    for widget in widgets:
        widget_type = widget.get("type")
        x = widget.get("x", 0)
        y = widget.get("y", 0)
        content = widget.get("content", {})

        if widget_type == "rectangular":
            w = widget.get("w", 4 * inch)
            h = widget.get("h", 3 * inch)
            draw_rectangular_widget(c, x, y, w, h, content, fonts)
            if "sources" in content:
                all_sources.extend(content["sources"])
        elif widget_type == "square":
            size = widget.get("size", 2 * inch)
            draw_square_widget(c, x, y, size, content, fonts)

    # ========== Page 2: Sources ==========
    if all_sources:
        c.showPage()
        c.setFillColor(colors.HexColor("#1E1E24"))
        c.rect(0, 0, width, height, stroke=0, fill=1)
        
        c.setFillColor(colors.white)
        c.setFont(fonts["bold"], 24)
        c.drawString(1 * inch, height - 1 * inch, "Sources")
        
        c.setFont(fonts["regular"], 12)
        source_y = height - 1.5 * inch
        
        unique_sources = {s['id']: s for s in all_sources}.values()

        for source in unique_sources:
            c.bookmarkPage(source['id'])
            c.addOutlineEntry(source['label'], source['id'], 0, 0)
            c.drawString(1 * inch, source_y, f"{source['label']}: {source['details']}")
            source_y -= 0.5 * inch

    c.save()
    print(f"Successfully created PDF: {output_filename}")

# =========
# Demo main
# =========

if __name__ == "__main__":
    os.makedirs("assets/fonts", exist_ok=True)

    if not os.path.exists("assets/banner-2.jpg"):
        img = Image.new('RGB', (1200, 1800), color=(28, 28, 30))
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("arial.ttf", 60)
        except IOError:
            font = ImageFont.load_default()
        d.text((100, 800), "Placeholder Image\nReplace with assets/banner-2.jpg",
               fill=(200, 200, 200), font=font)
        img.save("assets/banner-2.jpg")
        print("Created placeholder 'assets/banner-2.jpg'.")

    A4_WIDTH, A4_HEIGHT = A4
    margin = 0.5 * inch
    
    layout = [
        {
            "type": "rectangular",
            "x": margin, "y": A4_HEIGHT - 3 * inch,
            "w": A4_WIDTH - 2 * margin, "h": 2.5 * inch,
            "content": {
                "title": "Clause 1: Termination",
                "severity": "red",
                "text": "The termination clause appears to be one-sided, granting the other party broad rights to terminate for convenience without penalty, while our rights are limited to termination for cause.",
                "sources": [
                    {"label": "Source A", "id": "source_A", "details": "Contract Law Review, Vol. 3, Issue 4"},
                    {"label": "Source B", "id": "source_B", "details": "Internal Legal Precedent #1138"}
                ]
            }
        },
        {
            "type": "rectangular",
            "x": margin, "y": A4_HEIGHT - 6 * inch,
            "w": A4_WIDTH - 2 * margin, "h": 2.5 * inch,
            "content": {
                "title": "Clause 2: Liability",
                "severity": "yellow",
                "text": "The liability cap is set at a standard industry level, but does not account for potential damages from data breaches, which could exceed this cap. Recommend further review.",
                "sources": [
                    {"label": "Source C", "id": "source_C", "details": "2024 Tech Industry Risk Report"}
                ]
            }
        },
        {
            "type": "rectangular",
            "x": margin, "y": A4_HEIGHT - 9 * inch,
            "w": A4_WIDTH - 2 * margin, "h": 2.5 * inch,
            "content": {
                "title": "Clause 3: Confidentiality",
                "severity": "grey",
                "text": "The confidentiality obligations are standard and reciprocal, with a defined term of 5 years post-termination. This clause meets our internal guidelines.",
                "sources": [
                    {"label": "Source D", "id": "source_D", "details": "Corporate Policy Handbook, Section 5.2"}
                ]
            }
        },
    ]

    create_pdf_layout(widgets=layout)
