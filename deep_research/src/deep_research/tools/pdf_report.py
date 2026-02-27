"""
PDF Report Generator — converts markdown CI report to professional PDF.
"""

import re
from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

DARK = HexColor("#1a1a2e")
BLUE = HexColor("#0f3460")
GRAY = HexColor("#666666")
LIGHT_GRAY = HexColor("#f0f0f0")
GREEN = HexColor("#2d6a4f")
ORANGE = HexColor("#e76f51")
RED = HexColor("#c1121f")


def _get_styles():
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="ReportTitle",
            parent=styles["Title"],
            fontSize=24,
            leading=30,
            textColor=DARK,
            spaceAfter=6,
            alignment=TA_LEFT,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportSubtitle",
            parent=styles["Normal"],
            fontSize=12,
            leading=16,
            textColor=GRAY,
            spaceAfter=20,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H1",
            parent=styles["Heading1"],
            fontSize=18,
            leading=24,
            textColor=DARK,
            spaceBefore=24,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H2",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=BLUE,
            spaceBefore=16,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H3",
            parent=styles["Heading3"],
            fontSize=12,
            leading=16,
            textColor=DARK,
            spaceBefore=12,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportBody",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=DARK,
            spaceAfter=6,
            alignment=TA_JUSTIFY,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BulletItem",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
            textColor=DARK,
            leftIndent=20,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Source",
            parent=styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=GRAY,
            leftIndent=10,
            spaceAfter=2,
        )
    )
    return styles


def _escape_xml(text: str) -> str:
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    return text


def _style_confidence(text: str) -> str:
    text = text.replace("[HIGH]", '<font color="#2d6a4f"><b>[HIGH]</b></font>')
    text = text.replace("[MEDIUM]", '<font color="#e76f51"><b>[MEDIUM]</b></font>')
    text = text.replace("[LOW]", '<font color="#c1121f"><b>[LOW]</b></font>')
    text = text.replace(
        "[UNVERIFIED]", '<font color="#c1121f"><b>[UNVERIFIED]</b></font>'
    )
    text = text.replace(
        "[LOW-MEDIUM]", '<font color="#e76f51"><b>[LOW-MEDIUM]</b></font>'
    )
    return text


def _add_header_footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(BLUE)
    canvas.setLineWidth(0.5)
    canvas.line(2 * cm, A4[1] - 1.5 * cm, A4[0] - 2 * cm, A4[1] - 1.5 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GRAY)
    canvas.drawString(
        2 * cm, A4[1] - 1.3 * cm, "Deep Research — Competitive Intelligence Report"
    )
    canvas.drawRightString(A4[0] - 2 * cm, A4[1] - 1.3 * cm, "CONFIDENTIAL")
    canvas.line(2 * cm, 1.5 * cm, A4[0] - 2 * cm, 1.5 * cm)
    canvas.drawString(2 * cm, 0.8 * cm, f"Generated {datetime.now():%Y-%m-%d %H:%M}")
    canvas.drawRightString(A4[0] - 2 * cm, 0.8 * cm, f"Page {doc.page}")
    canvas.restoreState()


def _build_table(rows, styles):
    """Build a reportlab Table from parsed markdown table rows."""
    if not rows:
        return Spacer(1, 0)

    table_data = []
    for row in rows:
        styled_row = []
        for cell in row:
            text = _escape_xml(cell)
            text = _style_confidence(text)
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            styled_row.append(Paragraph(text, styles["ReportBody"]))
        table_data.append(styled_row)

    if not table_data:
        return Spacer(1, 0)

    num_cols = max(len(r) for r in table_data)
    available = A4[0] - 4 * cm
    col_width = available / num_cols

    for row in table_data:
        while len(row) < num_cols:
            row.append(Paragraph("", styles["ReportBody"]))

    t = Table(table_data, colWidths=[col_width] * num_cols)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GRAY),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#cccccc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return t


def markdown_to_pdf(md_path: str, target: str, output_path: str = None) -> str:
    if output_path is None:
        slug = re.sub(r"[^\w\-]", "_", target)[:50]
        ts = datetime.now().strftime("%Y%m%d_%H%M")
        output_dir = Path(md_path).parent
        output_path = str(output_dir / f"{slug}_report_{ts}.pdf")

    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    styles = _get_styles()
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
    )
    story = []

    # Title page
    story.append(Spacer(1, 4 * cm))
    story.append(Paragraph("Competitive Intelligence Report", styles["ReportTitle"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(width="100%", thickness=2, color=BLUE))
    story.append(Spacer(1, 0.5 * cm))
    story.append(
        Paragraph(
            _escape_xml(target),
            ParagraphStyle(
                "TargetName", parent=styles["ReportTitle"], fontSize=28, textColor=BLUE
            ),
        )
    )
    story.append(Spacer(1, 1 * cm))
    story.append(
        Paragraph(
            f"Generated: {datetime.now():%B %d, %Y at %H:%M}", styles["ReportSubtitle"]
        )
    )
    story.append(
        Paragraph("Deep Research Multi-Agent System", styles["ReportSubtitle"])
    )
    story.append(PageBreak())

    # Parse markdown
    lines = md_content.split("\n")
    table_rows = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            if table_rows:
                story.append(_build_table(table_rows, styles))
                table_rows = []
            continue

        # Table rows
        if "|" in stripped and stripped.startswith("|"):
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                continue
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            table_rows.append(cells)
            continue

        # Flush pending table
        if table_rows:
            story.append(_build_table(table_rows, styles))
            table_rows = []

        # Headers
        if stripped.startswith("# "):
            text = _style_confidence(_escape_xml(stripped[2:]))
            story.append(Paragraph(text, styles["H1"]))
            story.append(
                HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=8)
            )
            continue
        if stripped.startswith("## "):
            text = _style_confidence(_escape_xml(stripped[3:]))
            story.append(Paragraph(text, styles["H2"]))
            continue
        if stripped.startswith("### "):
            text = _style_confidence(_escape_xml(stripped[4:]))
            story.append(Paragraph(text, styles["H3"]))
            continue
        if stripped.startswith("#### "):
            text = _style_confidence(_escape_xml(stripped[5:]))
            story.append(Paragraph(f"<b>{text}</b>", styles["ReportBody"]))
            continue

        # Horizontal rules
        if stripped in ("---", "***", "___"):
            story.append(
                HRFlowable(
                    width="100%", thickness=0.5, color=GRAY, spaceBefore=8, spaceAfter=8
                )
            )
            continue

        # Bullets
        if stripped.startswith("- ") or stripped.startswith("* "):
            text = _escape_xml(stripped[2:])
            text = _style_confidence(text)
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            story.append(Paragraph(f"&bull; {text}", styles["BulletItem"]))
            continue

        # Numbered lists
        m = re.match(r"^(\d+)\.\s(.+)", stripped)
        if m:
            text = _escape_xml(m.group(2))
            text = _style_confidence(text)
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            story.append(Paragraph(f"{m.group(1)}. {text}", styles["BulletItem"]))
            continue

        # Source lines
        if stripped.startswith("[Source:") or stripped.startswith("Source:"):
            story.append(Paragraph(_escape_xml(stripped), styles["Source"]))
            continue

        # Regular paragraph
        text = _escape_xml(stripped)
        text = _style_confidence(text)
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
        story.append(Paragraph(text, styles["ReportBody"]))

    # Flush final table
    if table_rows:
        story.append(_build_table(table_rows, styles))

    doc.build(story, onFirstPage=_add_header_footer, onLaterPages=_add_header_footer)
    print(f"✅ PDF generated: {output_path}")
    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pdf_report.py <markdown_file> [target_name]")
        sys.exit(1)
    markdown_to_pdf(
        sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "Research Target"
    )
