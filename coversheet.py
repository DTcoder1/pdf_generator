# pip install reportlab pillow

import os
from typing import Literal, Tuple

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape  # keep landscape available if needed
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
    return pdfmetrics.stringWidth(text, font_name, font_size)

def wrap_text_to_width(text: str, font_name: str, font_size: float, max_width: float):
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

def draw_accent_bar(c, x, y, w, h, *, fill_hex="#4C8DF6", alpha=0.9):
    col = colors.HexColor(fill_hex)
    c.setFillColor(colors.Color(col.red, col.green, col.blue, alpha=alpha))
    c.rect(x, y, w, h, stroke=0, fill=1)

def draw_text_block(
    c,
    *,
    x, y, w,  # panel origin (bottom-left) and width
    title, subtitle, meta_left, meta_right,
    fonts,  # dict with names: {"bold":..., "light":..., "regular":...}
    sizes,  # dict with sizes: {"title":..,"title_min":..,"subtitle":..,"meta":..}
    colors_cfg,  # dict with hex colors: {"title":..,"subtitle":..,"meta":..,"accent":..,"panel":..}
    padding=18,
    line_gap=10,
    tighten_titles=True,
    panel_opacity=0.42,
    show_panel=True,
    accent_on_left=True,
):
    """
    Draw a text panel with auto-fit title, wrapped subtitle, and two meta lines.
    Returns (x, y, w, panel_h).
    """
    inner_x = x + padding
    max_title_width = w - 2 * padding
    max_subtitle_width = w - 2 * padding

    # Colors
    title_color = colors.HexColor(colors_cfg.get("title", "#FFFFFF"))
    subtitle_color = colors.HexColor(colors_cfg.get("subtitle", "#EDEDED"))
    meta_color = colors.HexColor(colors_cfg.get("meta", "#CFCFCF"))
    accent_hex = colors_cfg.get("accent", "#4C8DF6")
    panel_hex = colors_cfg.get("panel", "#05070B")

    # Title (auto-fit)
    title_size = sizes.get("title", 52)
    title_min = sizes.get("title_min", 28)
    if tighten_titles:
        title_size = auto_fit_font_size(title, fonts["bold"], max_title_width, title_size, title_min)
    title_h = title_size  # 1em baseline

    # Subtitle (wrap)
    subtitle_size = sizes.get("subtitle", 22)
    subtitle_lines = wrap_text_to_width(subtitle, fonts["light"], subtitle_size, max_subtitle_width)
    subtitle_line_h = subtitle_size * 1.15
    subtitle_block_h = len(subtitle_lines) * subtitle_line_h if subtitle_lines else 0

    # Meta
    meta_size = sizes.get("meta", 10)
    meta_line_h = meta_size * 1.2
    meta_block_h = meta_line_h * 2

    # Height
    content_h = title_h + line_gap + subtitle_block_h + line_gap + meta_block_h
    panel_h = content_h + padding * 2

    # Accent + Panel
    """
    if accent_on_left:
        draw_accent_bar(c, x, y, 4, panel_h, fill_hex=accent_hex, alpha=0.9)
    """
    if show_panel:
        draw_rounded_panel(c, x, y, w, panel_h, radius=14, fill_hex=panel_hex, alpha=panel_opacity, stroke=0)

    # Draw TITLE
    c.setFillColor(title_color)
    c.setFont(fonts["bold"], title_size)
    c.drawString(inner_x, y + panel_h - padding - title_h, title)

    # Draw SUBTITLE
    c.setFillColor(subtitle_color)
    c.setFont(fonts["light"], subtitle_size)
    sub_y = y + panel_h - padding - title_h - line_gap - subtitle_size
    for line in subtitle_lines:
        c.drawString(inner_x, sub_y, line)
        sub_y -= subtitle_line_h

    # Draw META (right-aligned)
    right_margin = x + w - padding
    c.setFillColor(meta_color)
    c.setFont(fonts["regular"], meta_size)
    c.drawRightString(right_margin, y + padding + meta_line_h, meta_left)
    c.drawRightString(right_margin, y + padding, meta_right)

    return (x, y, w, panel_h)

# ====================
# Background image util
# ====================

def draw_cover_image(
    c,
    image_path: str,
    page_size: Tuple[float, float],
    *,
    offset_x: float = 0,
    offset_y: float = 0,
    offset_mode: Literal["points", "percent_overflow"] = "percent_overflow",
    darken: float = 0.0,  # 0.0 = none, 1.0 = black
):
    """
    Draw an image to cover the full page (like CSS background-size: cover),
    allow offset without changing scale, and optionally darken.
    """
    width, height = page_size

    if not os.path.exists(image_path):
        # fallback solid background
        c.setFillColor(colors.HexColor("#1c1c1e"))
        c.rect(0, 0, width, height, stroke=0, fill=1)
        return

    img = ImageReader(image_path)
    img_w, img_h = img.getSize()
    img_aspect = img_h / float(img_w)

    # Cover-fit sizing
    draw_h = height
    draw_w = draw_h / img_aspect
    if draw_w < width:
        draw_w = width
        draw_h = draw_w * img_aspect

    # Base centered
    x = (width - draw_w) / 2.0
    y = (height - draw_h) / 2.0

    # Overflow in each axis (how much is cropped)
    overflow_x = max(0.0, draw_w - width)
    overflow_y = max(0.0, draw_h - height)

    # Offsets
    if offset_mode == "percent_overflow":
        x += offset_x * overflow_x   # e.g., -0.15 shows more right side
        y += offset_y * overflow_y
    else:
        x += offset_x                 # absolute points
        y += offset_y

    # Draw
    c.drawImage(img, x, y, width=draw_w, height=draw_h, mask='auto')

    # Optional darken overlay
    if darken > 0:
        darken = max(0.0, min(1.0, darken))
        c.setFillColor(colors.Color(0, 0, 0, alpha=darken))
        c.rect(0, 0, width, height, stroke=0, fill=1)

# ===========
# Main builder
# ===========

def create_modern_cover_sheet(
    output_filename="report_cover_modern.pdf",

    # -------- LOGO --------
    logo_path: str = "assets/logo.png",
    logo_width: float = 1.2 * inch,
    logo_margin: Tuple[float, float] = (0.6 * inch, 0.6 * inch),
    
    *,
    page_size=A4,  # or landscape(A4)
    # -------- CONTENT --------
    report_title="Contract Analysis Report",
    report_subtitle="Q3 2025 Market Analysis",
    author_name="Marketing Division",
    report_date="August 27, 2025",
    image_path="assets/banner-2.jpg",
    # -------- THEME / FONTS --------
    fonts_path="assets/fonts",
    font_files=("Poppins-Bold.ttf", "Poppins-Light.ttf", "Poppins-Regular.ttf"),
    # -------- IMAGE CONTROLS --------
    img_offset_x=-0.15,  # % overflow (negative = nudge right)
    img_offset_y=0.00,
    img_offset_mode="percent_overflow",
    img_darken=0.35,     # global background darken
    # -------- PANEL CONTROLS --------
    panel_width_ratio=0.65,  # fraction of page width
    panel_margin_left=1 * inch,
    panel_margin_bottom=0.9 * inch,
    panel_opacity=0.42,
    panel_color="#05070B",
    accent_on_left=True,
    # -------- TYPE SCALE --------
    sizes=None,  # if None, defaults applied
    colors_cfg=None,  # if None, defaults applied
    tighten_titles=True,
):
    """
    Build the cover with all controls above.
    """

    # ========== Fonts ==========
    bold_file, light_file, regular_file = font_files
    poppins_bold_path = os.path.join(fonts_path, bold_file)
    poppins_light_path = os.path.join(fonts_path, light_file)
    poppins_regular_path = os.path.join(fonts_path, regular_file)

    font_bold_name = "Helvetica-Bold"
    if os.path.exists(poppins_bold_path):
        pdfmetrics.registerFont(TTFont("Poppins-Bold", poppins_bold_path))
        font_bold_name = "Poppins-Bold"
    else:
        print(f"Warning: Bold font not found at '{poppins_bold_path}'. Using default bold.")

    font_light_name = "Helvetica"  # fallback
    if os.path.exists(poppins_light_path):
        pdfmetrics.registerFont(TTFont("Poppins-Light", poppins_light_path))
        font_light_name = "Poppins-Light"
    else:
        print(f"Warning: Light font not found at '{poppins_light_path}'. Using default.")

    font_regular_name = "Helvetica"
    if os.path.exists(poppins_regular_path):
        pdfmetrics.registerFont(TTFont("Poppins-Regular", poppins_regular_path))
        font_regular_name = "Poppins-Regular"
    else:
        print(f"Warning: Regular font not found at '{poppins_regular_path}'. Using default.")

    fonts = {
        "bold": font_bold_name,
        "light": font_light_name,
        "regular": font_regular_name,
    }

    # Defaults if not provided
    if sizes is None:
        sizes = {"title": 52, "title_min": 28, "subtitle": 22, "meta": 10}
    if colors_cfg is None:
        colors_cfg = {
            "title": "#FFFFFF",
            "subtitle": "#EAEAEA",
            "meta": "#D0D0D0",
            "accent": "#4C8DF6",
            "panel": panel_color,
        }

    # ========== Canvas ==========
    c = canvas.Canvas(output_filename, pagesize=page_size)
    width, height = page_size

    # ========== Background ==========
    draw_cover_image(
        c,
        image_path,
        (width, height),
        offset_x=img_offset_x,
        offset_y=img_offset_y,
        offset_mode=img_offset_mode,  # "percent_overflow" or "points"
        darken=img_darken,
    )

    # (Optional) If you still want a global translucent veil on top of the already darkened image,
    # uncomment these 2 lines and tweak alpha:
    # c.setFillColor(colors.Color(0, 0, 0, alpha=0.15))
    # c.rect(0, 0, width, height, stroke=0, fill=1)

    # ========== Text Panel ==========
    panel_w = min(width * panel_width_ratio, width - 2 * inch)
    panel_x = panel_margin_left
    panel_y = panel_margin_bottom

    draw_text_block(
        c,
        x=panel_x, y=panel_y, w=panel_w,
        title=report_title,
        subtitle=report_subtitle,
        meta_left=author_name,
        meta_right=report_date,
        fonts=fonts,
        sizes=sizes,
        colors_cfg=colors_cfg,
        padding=18,
        line_gap=10,
        tighten_titles=tighten_titles,
        panel_opacity=panel_opacity,
        show_panel=True,
        accent_on_left=accent_on_left,
    )
    
    # ========== Logo ==========
    if logo_path and os.path.exists(logo_path):
        try:
            logo = ImageReader(logo_path)
            logo_w = logo_width
            logo_h = logo_w * (logo.getSize()[1] / logo.getSize()[0])  # preserve aspect
            margin_x, margin_y = logo_margin
            c.drawImage(
                logo,
                margin_x,
                height - logo_h - margin_y,  # top-left placement
                width=logo_w,
                height=logo_h,
                mask='auto'
            )
        except Exception as e:
            print(f"Warning: could not draw logo: {e}")

    # ========== Save ==========
    c.save()
    print(f"Successfully created modern cover sheet: {output_filename}")

# =========
# Demo main
# =========

if __name__ == "__main__":
    # Ensure assets
    if not os.path.exists("assets"):
        os.makedirs("assets")
    if not os.path.exists("assets/fonts"):
        os.makedirs("assets/fonts")
        print("Created 'assets/fonts'. Add Poppins .ttf here (Bold/Light/Regular) for best look.")

    # Placeholder image if missing
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

    # Example call (tweak knobs here)
    create_modern_cover_sheet(
        output_filename="Contract Analysis Report.pdf",
        page_size=A4,  # or landscape(A4)
        report_title="Business Contract Review",
        report_subtitle="AI-Powered Insights by FreyAI",
        author_name="visit our website at contract.freyai.au",
        report_date="August 27, 2025",
        image_path="assets/banner-2.jpg",

        # Image tweaks
        img_offset_x=-0.15,
        img_offset_y=0.00,
        img_offset_mode="percent_overflow",
        img_darken=0.35,

        # Panel tweaks
        panel_width_ratio=1,
        panel_margin_left=1 * inch,
        panel_margin_bottom=0.9 * inch,
        panel_opacity=0.42,
        panel_color="#05070B",
        accent_on_left=True,

        # Type/Color tweaks
        sizes={"title": 52, "title_min": 28, "subtitle": 22, "meta": 10},
        colors_cfg={"title": "#FFFFFF", "subtitle": "#EAEAEA", "meta": "#D0D0D0", "accent": "#4C8DF6", "panel": "#05070B"},
        tighten_titles=True,
    )
