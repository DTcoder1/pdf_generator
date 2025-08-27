# pip install reportlab
import os
import re
import json
import webbrowser

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Paragraph, Spacer, Table, TableStyle,
    NextPageTemplate, PageBreak, FrameBreak,
    KeepTogether, CondPageBreak
)
from reportlab.platypus import PageTemplate, Frame
import uuid

# =========================================================
#  Utilities
# =========================================================

GUTTER = 0.25 * inch  # same value you use for your two-column layout
def to_roman(n: int) -> str:
    """Convert an integer to a Roman numeral (1–3999)."""
    if not (0 < n < 4000):
        raise ValueError("Number out of range (must be 1–3999)")
    numerals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"),
    ]
    out = []
    for val, sym in numerals:
        while n >= val:
            out.append(sym)
            n -= val
    return "".join(out)


def link_citations(text: str, link_color="#163b8a") -> str:
    """
    Replace [1], [1, 2], [1-3], [1–3] etc. with internal links to #ref_N.
    """
    def repl(m):
        inside = m.group(1)  # e.g., "1, 2" or "1-3"
        tokens = []
        for part in [p.strip() for p in inside.split(',') if p.strip()]:
            if any(d in part for d in ('-', '–', '—')):
                norm = part.replace('–', '-').replace('—', '-')
                try:
                    a, b = [int(x.strip()) for x in norm.split('-', 1)]
                except Exception:
                    tokens.append(part)
                    continue
                step = 1 if a <= b else -1
                nums = list(range(a, b + step, step))
                linked = '–'.join(
                    f'<link href="#ref_{n}"><font color="{link_color}">{n}</font></link>'
                    for n in nums
                )
                tokens.append(linked)
            else:
                try:
                    n = int(part)
                    tokens.append(f'<link href="#ref_{n}"><font color="{link_color}">{n}</font></link>')
                except ValueError:
                    tokens.append(part)
        return '[' + ', '.join(tokens) + ']'

    return re.sub(r'\[([0-9,\-\u2013\u2014\s]+)\]', repl, text)


# =========================================================
#  Author table (3 columns, wrap to new rows)
# =========================================================
def build_author_table(authors, doc, styles):
    """Return a 3-column author table that wraps to new rows as needed."""
    def author_cell(a):
        inner = Table(
            [[Paragraph(a['name'], styles['AuthorName'])],
             [Paragraph(a['institution'], styles['AuthorInfo'])],
             [Paragraph(a.get('contact', ''), styles['AuthorInfo'])]],
            colWidths=[doc.width / 3.0]
        )
        inner.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
            ('TOPPADDING', (0, 0), (-1, -1), 0),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ]))
        return inner

    cells = [author_cell(a) for a in authors]
    rows = [cells[i:i+3] for i in range(0, len(cells), 3)]
    if rows and len(rows[-1]) < 3:
        for _ in range(3 - len(rows[-1])):
            rows[-1].append(Paragraph('', styles['AuthorInfo']))

    author_table = Table(rows, colWidths=[doc.width / 3.0] * 3, hAlign='CENTER')
    author_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    return author_table


# =========================================================
#  Table helper (inline or full-width)
# =========================================================
from reportlab.pdfbase.pdfmetrics import stringWidth

def _measure_text_width(txt, font_name='Times-Roman', font_size=9):
    """Crude single-line width estimate for autosizing columns."""
    return stringWidth(str(txt), font_name, font_size)

def _autosize_col_widths(headers, rows, max_width,
                         base_font='Times-Roman', header_font='Times-Bold',
                         font_size=9, min_col=36):
    """
    Compute preferred column widths from header+row content,
    then scale to fit max_width and fix rounding drift so the
    sum is EXACTLY max_width.
    """
    ncols = max(1, len(headers))
    desired = [0.0] * ncols

    # header widths
    for j, h in enumerate(headers):
        desired[j] = max(desired[j], _measure_text_width(h, header_font, font_size))

    # body widths
    for row in rows:
        for j in range(min(ncols, len(row))):
            desired[j] = max(desired[j], _measure_text_width(row[j], base_font, font_size))

    # padding (L+R = 8pt)
    desired = [max(min_col, w + 8) for w in desired]

    total = sum(desired)
    if total <= 0:
        return [max_width / ncols] * ncols

    # scale down if wider than available
    scale = min(1.0, max_width / total)
    widths = [w * scale for w in desired]

    # fix tiny drift so sum == max_width exactly
    delta = max_width - sum(widths)
    if abs(delta) > 0.01:
        widths[-1] += delta

    return widths

def make_fullwidth_then_two_col_template(doc, top_height, *, gutter, onPage):
    """
    Create a PageTemplate with:
      - top full-width frame of 'top_height'
      - two columns below sharing the remaining height
    """
    template_id = f"FW_{uuid.uuid4().hex[:8]}"

    # Geometry
    full_w = doc.width
    full_h = max(0, top_height)
    below_h = max(0, doc.height - full_h)

    # y-positions from bottom margin up
    full_y = doc.bottomMargin + below_h
    below_y = doc.bottomMargin

    # Columns below
    col_w = (doc.width - gutter) / 2.0
    left_x = doc.leftMargin
    right_x = doc.leftMargin + col_w + gutter

    top_full = Frame(doc.leftMargin, full_y, full_w, full_h, id=f"{template_id}_top")
    left_below = Frame(left_x, below_y, col_w, below_h, id=f"{template_id}_L")
    right_below = Frame(right_x, below_y, col_w, below_h, id=f"{template_id}_R")

    return PageTemplate(
        id=template_id,
        frames=[top_full, left_below, right_below],
        onPage=onPage  # <- important so header/footer still renders
    )

def _measure_fullwidth_table_height(headers, rows, *, doc, styles, col_widths=None):
    """Build the caption+table once, wrap at doc.width, and return (flow, total_height)."""
    flow = make_table_flowables(
        headers=headers, rows=rows, caption=None,  # caption measured separately
        doc=doc, styles=styles, col_widths=col_widths, max_width=doc.width
    )
    # flow = [Paragraph(caption)?, Table]
    # We'll create caption separately so we can measure both pieces.

    # 1) a dummy caption (just to measure when caller has a string)
    def make_caption(txt):
        return Paragraph(txt, styles['TableCaption'])

    def measure(flowables, max_w):
        h_total = 0
        for fl in flowables:
            w, h = fl.wrap(max_w, 10**6)
            h_total += h
        return h_total

    return flow, measure

def make_table_flowables(*,
    headers, rows, caption=None, doc=None, styles=None,
    col_widths=None, zebra=True, max_width=None, wrap_mode='normal'
):
    assert styles is not None and doc is not None

    total_w = max_width if max_width is not None else doc.width

    header_cells = [Paragraph(str(h), styles['TableHeaderCell']) for h in headers]
    body_cells = [[Paragraph(str(c), styles['TableCell']) for c in row] for row in rows]

    if col_widths is None:
        col_widths = _autosize_col_widths(headers, rows, total_w)

    data = [header_cells] + body_cells

    tbl = Table(data, colWidths=col_widths, hAlign='CENTER', repeatRows=1)
    base = [
        ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#E5E7EB')),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DBEAFE')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#111827')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),

        # keep individual cells from splitting across pages
        ('SPLITINROW', (0, 0), (-1, -1), 0),
        # If you ever enable table-level NOSPLIT, remember: no 4th arg!
        # ('NOSPLIT', (0, 0), (-1, -1)),
    ]

    if wrap_mode and wrap_mode.lower() == 'cjk':
        base.append(('WORDWRAP', (0, 0), (-1, -1), 'CJK'))

    if zebra and rows:
        base.append(('ROWBACKGROUNDS', (0, 1), (-1, -1),
                     [colors.HexColor('#F3F4F6'), colors.white]))

    tbl.setStyle(TableStyle(base))

    out = []
    if caption:
        out.append(Paragraph(caption, styles['TableCaption']))
    out.append(tbl)
    return out

def measure_fullwidth_table_group(*,
    headers, rows, caption_text, doc, styles, col_widths=None,
    spacer_after=0.06 * inch
):
    caption_para = Paragraph(caption_text, styles['TableCaption'])
    table_flow = make_table_flowables(
        headers=headers, rows=rows, caption=None,
        doc=doc, styles=styles, col_widths=col_widths, max_width=doc.width
    )

    # ✅ Correct NOSPLIT usage (no 4th arg)
    if table_flow and hasattr(table_flow[-1], "setStyle"):
        table_flow[-1].setStyle(TableStyle([('NOSPLIT', (0, 0), (-1, -1))]))

    total_h = 0
    _, ch = caption_para.wrap(doc.width, 10**6); total_h += ch
    for fl in table_flow:
        _, fh = fl.wrap(doc.width, 10**6); total_h += fh

    total_h += spacer_after
    return caption_para, table_flow, total_h

# --- Image helpers -----------------------------------------------------------
from reportlab.platypus import Image as RLImage, Paragraph
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import inch

def make_image_flowables(
    *,
    path,                  # file path or file-like
    caption=None,          # string or None
    doc=None,
    styles=None,
    max_width=None,        # e.g., (doc.width - GUTTER)/2 for inline column; doc.width for full-width
    max_height=None,       # optional hard cap; defaults to no vertical cap
    hAlign='CENTER'
):
    """
    Return [caption?, Image] sized to fit max_width (and max_height if given),
    preserving aspect ratio. Ready to insert into story.
    """
    assert doc is not None and styles is not None

    total_w = max_width if max_width is not None else doc.width

    img = RLImage(path)
    img.hAlign = hAlign

    # Natural pixels
    iw, ih = float(img.imageWidth), float(img.imageHeight)

    # Constraints
    max_w = float(total_w)
    max_h = float(max_height) if max_height else None

    # Compute uniform scale to fit within (max_w, max_h) while preserving aspect
    if max_h:
        s = min(max_w / iw, max_h / ih, 1.0 if (iw <= max_w and ih <= max_h) else 10**9)
    else:
        s = min(max_w / iw, 1.0 if iw <= max_w else 10**9)

    img.drawWidth  = iw * s
    img.drawHeight = ih * s

    out = []
    if caption:
        out.append(Paragraph(str(caption), styles['TableCaption']))  # reuse your caption style
    out.append(img)
    return out

def measure_fullwidth_image_group(
    *,
    path,
    caption_text,
    doc,
    styles,
    max_height=None,           # optional vertical cap for the image itself
    spacer_after=0.06 * inch   # keep in sync with the Spacer you add after drawing
):
    """
    Build caption + full-width image (no caption inside list),
    measure total height at doc.width. Returns:
      (caption_para, [image_only], total_height_pts)
    """
    caption_para = Paragraph(caption_text, styles['TableCaption'])
    image_flow   = make_image_flowables(
        path=path, caption=None, doc=doc, styles=styles,
        max_width=doc.width, max_height=max_height, hAlign='CENTER'
    )

    total_h = 0.0
    # caption height
    _, ch = caption_para.wrap(doc.width, 10**6); total_h += ch
    # image height (the list has exactly one RLImage)
    for fl in image_flow:
        _, fh = fl.wrap(doc.width, 10**6); total_h += fh

    total_h += spacer_after
    return caption_para, image_flow, total_h

# =========================================================
#  Main builder
# =========================================================
def create_research_paper_pdf(metadata, body_content, references_content, *, output_filename="research_paper_enhanced.pdf"):
    """
    Build a research paper PDF with:
      - First page: single column (title/abstract)
      - Body: true two-column frames (no mid-page balancing)
      - Headings kept with content; clean column/page breaks
      - Inline & full-width tables with captions
      - Clickable citations [1, 2–4] -> reference list
      - References page in single column
    """
    # -----------------------------
    # Doc + page templates
    # -----------------------------
    doc = BaseDocTemplate(
        output_filename,
        pagesize=(8.5 * inch, 11 * inch),
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=1.0 * inch,
        bottomMargin=1.0 * inch,
    )

    # Header/Footer
    def header_footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont('Times-Roman', 9)
        if doc_.page > 1:
            pub_info = metadata.get('publication_info', {})
            header_text = (f"{pub_info.get('journal', '')}, Vol. {pub_info.get('volume', 'N/A')}, "
                           f"No. {pub_info.get('issue', 'N/A')}, {pub_info.get('date', '')}")
            canvas.drawString(doc.leftMargin, 10.5 * inch, header_text)
            canvas.line(doc.leftMargin, 10.45 * inch, doc.width + doc.leftMargin, 10.45 * inch)
        canvas.drawCentredString(4.25 * inch, 0.5 * inch, f"Page {doc_.page}")
        canvas.restoreState()

    # First page: single frame
    first_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="first_frame")

    # Body: two columns
    gutter = 0.25 * inch
    col_w = (doc.width - gutter) / 2.0
    left_col = Frame(doc.leftMargin, doc.bottomMargin, col_w, doc.height, id="left_col")
    right_col = Frame(doc.leftMargin + col_w + gutter, doc.bottomMargin, col_w, doc.height, id="right_col")

    # One-column body (for full-width tables/figures)
    onecol_body_frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="onecol_body_frame")

    first_template   = PageTemplate(id="First",     frames=[first_frame],      onPage=header_footer)
    twocol_template  = PageTemplate(id="TwoCol",    frames=[left_col, right_col], onPage=header_footer)
    onecol_template  = PageTemplate(id="OneColBody", frames=[onecol_body_frame],  onPage=header_footer)
    doc.addPageTemplates([first_template, twocol_template, onecol_template])

    # -----------------------------
    # Styles
    # -----------------------------
    neutral_dark = colors.HexColor("#111827")
    neutral_medium_dark = colors.HexColor("#374151")

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name='PaperTitle', fontName='Times-Bold', fontSize=22, leading=26,
        alignment=TA_CENTER, textColor=neutral_dark
    ))
    styles['BodyText'].fontName = 'Times-Roman'
    styles['BodyText'].fontSize = 10
    styles['BodyText'].leading = 12
    styles['BodyText'].alignment = TA_JUSTIFY
    styles.add(ParagraphStyle(
        name='BodyTextPadded', parent=styles['BodyText'], leftIndent=6, rightIndent=6
    ))
    styles.add(ParagraphStyle(
        name='AuthorName', fontName='Times-Roman', fontSize=11, leading=14,
        alignment=TA_CENTER, textColor=neutral_dark
    ))
    styles.add(ParagraphStyle(
        name='AuthorInfo', fontName='Times-Roman', fontSize=9, leading=12,
        alignment=TA_CENTER, textColor=neutral_medium_dark
    ))
    styles.add(ParagraphStyle(
        name='H2', fontName='Times-Roman', fontSize=12, leading=14,
        textColor=neutral_dark, spaceBefore=12, spaceAfter=6, keepWithNext=True
    ))
    styles.add(ParagraphStyle(
        name='Abstract', parent=styles['BodyText'], leftIndent=0.25 * inch, rightIndent=0.25 * inch
    ))
    styles.add(ParagraphStyle(
        name='ReferenceText', parent=styles['BodyText'], fontSize=9, leading=11,
        firstLineIndent=-0.25 * inch, leftIndent=0.25 * inch
    ))
    styles.add(ParagraphStyle(
        name='TableCaption', parent=styles['BodyText'], fontName='Times-Italic',
        fontSize=9, leading=11, spaceBefore=6, spaceAfter=6, alignment=TA_CENTER
    ))
    
    styles.add(ParagraphStyle(
        name='TableCell',
        parent=styles['BodyText'],
        fontSize=9,
        leading=11,
        alignment=TA_JUSTIFY,   # allows nice wrapping
    ))
    styles.add(ParagraphStyle(
        name='TableHeaderCell',
        parent=styles['TableCell'],
        fontName='Times-Bold',
        alignment=TA_CENTER
    ))

    # -----------------------------
    # Build story
    # -----------------------------
    story = []
    story.append(Paragraph(metadata['title'], styles['PaperTitle']))
    story.append(Spacer(1, 0.25 * inch))
    story.append(build_author_table(metadata['authors'], doc, styles))
    story.append(Spacer(1, 0.2 * inch))
    story.append(Paragraph(f"<b>Abstract—</b>{metadata['summary']}", styles['Abstract']))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph(f"<b><i>Keywords—</i></b>{', '.join(metadata.get('tags', []))}", styles['Abstract']))

    # Switch to two-column body on a new page
    story.append(NextPageTemplate("TwoCol"))
    story.append(PageBreak())

    section_idx = 1
    table_counter = 1

    for item in body_content:
        itype = item.get('type')

        if itype == 'section':
            story.append(CondPageBreak(0.8 * inch))
            heading = f"{to_roman(section_idx)}. {item['title'].upper()}"
            story.append(Paragraph(heading, styles['H2']))
            section_idx += 1

            paras = [Paragraph(link_citations(p), styles['BodyTextPadded'])
                     for p in (item.get('content') or [])]
            if paras:
                glued = [paras[0]]
                if len(paras) > 1:
                    glued.append(paras[1])
                story.append(KeepTogether(glued))
                story.extend(paras[2:])
            story.append(Spacer(1, 0.06 * inch))
            
        elif itype == 'image' and (item.get('placement','inline').lower() == 'inline'):
            img_path   = item['path']           # or however you store it
            caption    = item.get('caption')
            max_h_in   = item.get('max_height_pts')  # optional

            flow = make_image_flowables(
                path=img_path,
                caption=caption,
                doc=doc, styles=styles,
                max_width=(doc.width - GUTTER) / 2.0,   # column width
                max_height=max_h_in
            )
            # keep together so caption doesn't separate from image
            story.append(KeepTogether(flow))
            story.append(Spacer(1, 0.08 * inch))
            
        elif itype == 'image' and (item.get('placement','inline').lower() == 'fullwidth'):
            img_path   = item['path']
            caption    = item.get('caption') or "Figure"
            max_h_fw   = item.get('max_height_pts')    # optional; e.g., 4*inch

            cap_para, image_flow, total_h = measure_fullwidth_image_group(
                path=img_path,
                caption_text=caption,
                doc=doc, styles=styles,
                max_height=max_h_fw,
                spacer_after=0.06 * inch
            )

            temp_tpl = make_fullwidth_then_two_col_template(
                doc, total_h, gutter=GUTTER, onPage=header_footer
            )
            doc.addPageTemplates([temp_tpl])

            story.append(NextPageTemplate(temp_tpl.id))
            story.append(PageBreak())
            story.append(cap_para)
            story.extend(image_flow)
            story.append(Spacer(1, 0.06 * inch))  # already included in total_h
            story.append(NextPageTemplate("TwoCol"))

        elif itype == 'table':
            headers    = item.get('headers', [])
            rows       = item.get('rows', [])
            placement  = (item.get('placement') or 'inline').lower()
            caption    = item.get('caption')
            col_widths = item.get('col_widths')

            if not caption:
                base = item.get('title', 'Table')
                caption = f"Table {table_counter}. {base}"
            table_counter += 1

            if placement == 'inline':
                story.append(CondPageBreak(1.2 * inch))
                flow = make_table_flowables(
                    headers=headers, rows=rows, caption=caption,
                    doc=doc, styles=styles, col_widths=col_widths,
                    # >>> key line: size to the current column, not the full page
                    max_width=(doc.width - GUTTER) / 2.0
                )
                story.append(KeepTogether(flow))
                story.append(Spacer(1, 0.08 * inch))

            elif placement == 'fullwidth':
                if not caption:
                    base = item.get('title', 'Table')
                    caption = f"Table {table_counter}. {base}"

                cap_para, table_flow, total_h = measure_fullwidth_table_group(
                    headers=headers, rows=rows, caption_text=caption,
                    doc=doc, styles=styles, col_widths=col_widths,
                    spacer_after=0.06 * inch     # << keep this in sync with the Spacer below
                )

                temp_tpl = make_fullwidth_then_two_col_template(
                    doc, total_h, gutter=gutter, onPage=header_footer
                )
                doc.addPageTemplates([temp_tpl])

                story.append(NextPageTemplate(temp_tpl.id))
                story.append(PageBreak())
                story.append(cap_para)
                story.extend(table_flow)
                story.append(Spacer(1, 0.06 * inch))  # << already counted in total_h

                story.append(NextPageTemplate("TwoCol"))
                table_counter += 1
            else:
                # fallback
                flow = make_table_flowables(
                    headers=headers, rows=rows, caption=caption,
                    doc=doc, styles=styles, col_widths=col_widths
                )
                story.append(KeepTogether(flow))
                story.append(Spacer(1, 0.08 * inch))

    # References (single column for clarity)
    story.append(NextPageTemplate("First"))
    story.append(PageBreak())
    story.append(Paragraph("REFERENCES", styles['H2']))
    story.append(Spacer(1, 0.05 * inch))
    for i, ref in enumerate(references_content, 1):
        linked = f'<a name="ref_{i}"/>[{i}] {ref["text"]}'
        story.append(Paragraph(linked, styles['ReferenceText']))
        story.append(Spacer(1, 4))

    # Build
    try:
        doc.build(story)
        print(f"✅ Successfully generated {output_filename}")
        return os.path.abspath(output_filename)
    except Exception as e:
        print(f"❌ Failed to generate PDF. Error: {e}")
        return None


# =========================================================
#  CLI entry for testing from JSON
# =========================================================
if __name__ == "__main__":
    json_path = "paper_input.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    file_path = create_research_paper_pdf(
        metadata=data["metadata"],
        body_content=data["body_content"],
        references_content=data["references"],
        output_filename="research_paper_enhanced.pdf"
    )
    if file_path:
        webbrowser.open(f"file://{file_path}")
