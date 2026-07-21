"""Client-facing tax computation PDF (reportlab)."""
import io
from datetime import datetime, timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle)

GRAPHITE = colors.HexColor("#202020")
EMBER = colors.HexColor("#ff682c")
ASH = colors.HexColor("#efefef")
IVORY = colors.HexColor("#ebe6dd")
STEEL = colors.HexColor("#4d4d4d")
BRASS = colors.HexColor("#816729")


def _inr(v):
    try:
        return "Rs. " + format(int(round(float(v))), ",d")
    except Exception:
        return "Rs. 0"


def build_computation_pdf(filing: dict) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm)
    styles = getSampleStyleSheet()
    H = ParagraphStyle("H", parent=styles["Title"], fontName="Helvetica", fontSize=22,
                       textColor=GRAPHITE, spaceAfter=2, leading=24)
    sub = ParagraphStyle("sub", parent=styles["Normal"], fontSize=9, textColor=BRASS, spaceAfter=14)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12,
                        textColor=GRAPHITE, spaceBefore=14, spaceAfter=6)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=8, textColor=STEEL, leading=11)
    body = ParagraphStyle("body", parent=styles["Normal"], fontSize=9.5, textColor=STEEL, leading=13)

    payload = filing.get("parsed_payload") or {}
    c = filing.get("tax_computation_summary") or {}
    regime = filing.get("selected_regime", "NEW")
    rec = c.get("recommended_regime", "NEW")

    story = []
    story.append(Paragraph("Green Papaya — Tax Computation", H))
    story.append(Paragraph(f"{filing.get('assessment_year','AY 2026-27')}  ·  {filing.get('selected_itr_form','ITR-1')}  ·  Generated {datetime.now(timezone.utc).strftime('%d %b %Y')}", sub))

    info = [["Taxpayer", filing.get("user_name", "-")],
            ["Email", filing.get("user_email", "-")],
            ["Selected regime", regime],
            ["Recommended regime", rec]]
    t = Table(info, colWidths=[45 * mm, None])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (0, -1), STEEL),
        ("TEXTCOLOR", (1, 0), (1, -1), GRAPHITE),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, ASH),
    ]))
    story.append(t)

    story.append(Paragraph("Income & deductions", h2))
    inc = [["Component", "Amount"],
           ["Gross salary (u/s 17(1))", _inr(payload.get("gross_salary", 0))],
           ["Section 10 exemptions", _inr(payload.get("section_10_exemptions", 0))],
           ["Other income (interest/dividend)", _inr(payload.get("other_income", 0))],
           ["House property income", _inr(payload.get("house_property_income", 0))],
           ["Deductions u/s 80C", _inr(min(payload.get("deductions_80c", 0), 150000))],
           ["Deductions u/s 80D", _inr(payload.get("deductions_80d", 0))],
           ["STCG (equity)", _inr(payload.get("stcg_equity", 0))],
           ["LTCG (equity)", _inr(payload.get("ltcg_equity", 0))],
           ["TDS deducted", _inr(payload.get("tds_deducted", 0))]]
    story.append(_money_table(inc))

    story.append(Paragraph("Regime comparison", h2))
    comp = [["Metric", "Old Regime", "New Regime"],
            ["Taxable income", _inr(c.get("taxable_income_old", 0)), _inr(c.get("taxable_income_new", 0))],
            ["Base tax", _inr(c.get("base_tax_old", 0)), _inr(c.get("base_tax_new", 0))],
            ["Capital gains tax", _inr(c.get("stcg_tax", 0) + c.get("ltcg_tax", 0)), _inr(c.get("stcg_tax", 0) + c.get("ltcg_tax", 0))],
            ["Health & edu cess (4%)", _inr(c.get("cess_old", 0)), _inr(c.get("cess_new", 0))],
            ["Total tax liability", _inr(c.get("tax_liability_old", 0)), _inr(c.get("tax_liability_new", 0))]]
    ct = Table(comp, colWidths=[60 * mm, None, None])
    ct.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), GRAPHITE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("TEXTCOLOR", (0, 1), (-1, -1), GRAPHITE),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 1), (-1, -2), 0.4, ASH),
        ("BACKGROUND", (0, -1), (-1, -1), IVORY),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(ct)

    savings = c.get("savings_with_recommended", 0)
    story.append(Spacer(1, 8))
    story.append(Paragraph(f"<b>Recommendation:</b> Opt for the <b>{rec}</b> regime — estimated saving of <b>{_inr(savings)}</b> versus the alternative.", body))

    slabs = c.get("slabs_new" if regime == "NEW" else "slabs_old") or []
    if slabs:
        story.append(Paragraph(f"Slab-wise breakup ({regime} regime)", h2))
        rows = [["Slab", "Rate", "Taxable in slab", "Tax"]]
        for s in slabs:
            rows.append([s.get("label", ""), f"{int(s.get('rate',0)*100)}%",
                         _inr(s.get("taxable_amount", 0)), _inr(s.get("tax", 0))])
        story.append(_money_table(rows, cols=[35 * mm, 25 * mm, None, None]))

    flags = filing.get("reconciliation_discrepancies") or []
    if flags:
        story.append(Paragraph("AIS / 26AS reconciliation notes", h2))
        for f in flags:
            msg = str(f.get('message', '')).replace("₹", "Rs. ")
            story.append(Paragraph(f"• <b>{f.get('field')}</b> ({f.get('severity')}): {msg}", small))

    story.append(Spacer(1, 20))
    story.append(Paragraph("This computation is generated by Green Papaya for review purposes and does not constitute "
                           "professional accounting, financial or legal advice. Verify all figures with a qualified "
                           "Chartered Accountant before filing. Tax laws are subject to change.", small))

    doc.build(story)
    return buf.getvalue()


def _money_table(rows, cols=None):
    if cols is None:
        cols = [None, None]
    t = Table(rows, colWidths=cols)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("TEXTCOLOR", (0, 0), (-1, 0), GRAPHITE),
        ("TEXTCOLOR", (0, 1), (-1, -1), STEEL),
        ("ALIGN", (-1, 0), (-1, -1), "RIGHT"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, GRAPHITE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, ASH),
    ]))
    return t
