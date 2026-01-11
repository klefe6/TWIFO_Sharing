"""
Summary PDF Renderer

Converts __sum.json files to professional trader-focused PDF summaries.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.pdfgen import canvas
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


def compute_summary_score(summary: dict) -> tuple[int, str]:
    """
    Compute summary_score_0_100 using deterministic heuristic.
    
    Returns: (score: int, reason: str)
    """
    score = 50  # Start at 50
    reasons = []
    
    # +5 per actionable bullet (max +25)
    actionable = summary.get("actionable", [])
    actionable_count = len(actionable) if actionable else 0
    actionable_points = min(actionable_count * 5, 25)
    if actionable_points > 0:
        reasons.append(f"+{actionable_points} for {actionable_count} actionable items")
    score += actionable_points
    
    # Check per_product for key_levels, catalysts, risks, confidence
    per_product = summary.get("per_product", {})
    has_key_levels = False
    has_catalysts = False
    has_risks = False
    has_confidence = False
    
    for product_data in per_product.values():
        if isinstance(product_data, dict):
            if product_data.get("key_levels"):
                has_key_levels = True
            if product_data.get("catalysts"):
                has_catalysts = True
            if product_data.get("risks"):
                has_risks = True
            if product_data.get("confidence_0_100") is not None:
                has_confidence = True
    
    # +10 if key_levels present
    if has_key_levels:
        score += 10
        reasons.append("+10 for key levels")
    
    # +10 if catalysts present
    if has_catalysts:
        score += 10
        reasons.append("+10 for catalysts")
    
    # +10 if risks present
    if has_risks:
        score += 10
        reasons.append("+10 for risks")
    
    # +5 if confidence values exist
    if has_confidence:
        score += 5
        reasons.append("+5 for confidence scores")
    
    # -15 if actionable empty AND key_levels empty AND catalysts empty AND risks empty
    if actionable_count == 0 and not has_key_levels and not has_catalysts and not has_risks:
        score -= 15
        reasons.append("-15 for missing actionable content")
    
    # Clamp to [0, 100]
    score = max(0, min(100, score))
    
    reason_str = "; ".join(reasons) if reasons else "Base score"
    
    return score, reason_str


def get_score_color(score: int) -> tuple[float, float, float]:
    """
    Get RGB color tuple for score (0-10 scale).
    0 = dark red, 5 = yellow, 10 = green
    """
    if score <= 2:
        # 0-2: Dark red to red
        intensity = score / 2.0
        return (0.6 + 0.4 * intensity, 0.0, 0.0)
    elif score <= 5:
        # 3-5: Red to orange to yellow
        intensity = (score - 2) / 3.0
        return (1.0, 0.4 * intensity, 0.0)
    elif score <= 7:
        # 6-7: Yellow to yellow-green
        intensity = (score - 5) / 2.0
        return (1.0 - 0.3 * intensity, 1.0, 0.0)
    else:
        # 8-10: Light green to dark green
        intensity = (score - 7) / 3.0
        return (0.4 - 0.2 * intensity, 0.8 + 0.2 * intensity, 0.2 * intensity)


def render_summary_pdf(json_path: Path, output_path: Optional[Path] = None) -> Path:
    """
    Generate PDF summary from JSON file.
    
    Args:
        json_path: Path to __sum.json file
        output_path: Optional output path (defaults to json_path with .pdf extension)
    
    Returns:
        Path to generated PDF file
    """
    if not REPORTLAB_AVAILABLE:
        raise ImportError("reportlab is required for PDF generation. Install with: pip install reportlab")
    
    if not json_path.exists():
        raise FileNotFoundError(f"Summary JSON not found: {json_path}")
    
    # Load JSON
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in {json_path}: {e}")
    
    # Extract scores (0-10 scale from AI)
    score = summary.get("summary_score_0_10", 0)
    chart_score = summary.get("chart_score_0_3", 0)
    
    # Determine output path
    if output_path is None:
        output_path = json_path.with_suffix('.pdf')
    
    # Generate PDF
    doc = SimpleDocTemplate(str(output_path), pagesize=letter,
                           rightMargin=0.75*inch, leftMargin=0.75*inch,
                           topMargin=0.75*inch, bottomMargin=0.75*inch)
    
    # Container for PDF elements
    story = []
    styles = getSampleStyleSheet()
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#004080'),
        spaceAfter=12,
        fontName='Helvetica-Bold'
    )
    
    # Header style
    header_style = ParagraphStyle(
        'CustomHeader',
        parent=styles['Heading2'],
        fontSize=14,
        textColor=colors.HexColor('#004080'),
        spaceAfter=6,
        spaceBefore=12,
        fontName='Helvetica-Bold'
    )
    
    # Body style
    body_style = ParagraphStyle(
        'CustomBody',
        parent=styles['BodyText'],
        fontSize=10,
        spaceAfter=6,
        leading=12
    )
    
    # Extract original PDF name from JSON filename (remove __sum.json)
    original_name = json_path.stem.replace('__sum', '')
    
    # Title: Use original PDF name or fallback
    title_text = original_name.replace('_', ' ')
    story.append(Paragraph(title_text, title_style))
    story.append(Spacer(1, 0.2*inch))
    
    # Score indicator (colored box at top with both scores)
    score_color = get_score_color(score)
    
    # Chart score indicator (text-based)
    chart_indicators = ["⬜" * chart_score + "⬛" * (3 - chart_score)] if chart_score <= 3 else "⬜⬜⬜"
    
    score_table_data = [
        [f"<b>Summary Score: {score}/10</b>", f"<b>Charts: {chart_score}/3</b> {chart_indicators}"]
    ]
    score_table = Table(score_table_data, colWidths=[3.25*inch, 3.25*inch])
    score_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.Color(*score_color)),
        ('BACKGROUND', (1, 0), (1, 0), colors.lightgrey),
        ('TEXTCOLOR', (0, 0), (0, 0), colors.white),
        ('TEXTCOLOR', (1, 0), (1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 0.2*inch))
    
    # Product Categories (compact format at top)
    product_categories = summary.get("product_categories", {})
    if product_categories:
        # Format as: E (CL, NG), M (GC, SI), etc.
        cat_parts = []
        for cat_code, tickers in product_categories.items():
            tickers_str = ", ".join(tickers) if isinstance(tickers, list) else str(tickers)
            cat_parts.append(f"{cat_code} ({tickers_str})")
        categories_text = ", ".join(cat_parts)
        
        story.append(Paragraph(f"<b>Products:</b> {categories_text}", ParagraphStyle(
            'CategoriesText', parent=body_style, fontSize=10, spaceAfter=12
        )))
        story.append(Spacer(1, 0.1*inch))
    
    # Overall Bias and Time Horizon
    bias_table_data = []
    overall_bias = summary.get("overall_bias", "Not provided")
    time_horizon = summary.get("time_horizon", "Not provided")
    if overall_bias and overall_bias != "Not provided":
        overall_bias = overall_bias.capitalize()
    bias_table_data.append(["<b>Overall Bias:</b>", overall_bias])
    bias_table_data.append(["<b>Time Horizon:</b>", time_horizon])
    
    bias_table = Table(bias_table_data, colWidths=[1.5*inch, 5*inch])
    bias_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(bias_table)
    story.append(Spacer(1, 0.2*inch))
    
    # TL;DR Section
    story.append(Paragraph("<b>TL;DR</b>", header_style))
    tldr = summary.get("tldr", [])
    if tldr:
        for item in tldr:
            story.append(Paragraph(f"• {item}", body_style))
    else:
        story.append(Paragraph("<i>Not provided</i>", body_style))
    story.append(Spacer(1, 0.15*inch))
    
    # Actionable Section
    story.append(Paragraph("<b>Actionable</b>", header_style))
    actionable = summary.get("actionable", [])
    if actionable:
        for item in actionable:
            story.append(Paragraph(f"• {item}", body_style))
    else:
        story.append(Paragraph("<i>Not provided</i>", body_style))
    story.append(Spacer(1, 0.15*inch))
    
    # Per Product Section
    per_product = summary.get("per_product", {})
    products = summary.get("products", [])
    
    if per_product or products:
        story.append(Paragraph("<b>Per Product</b>", header_style))
        
        # If we have per_product data, show it
        if per_product:
            for product_name, product_data in per_product.items():
                if not isinstance(product_data, dict):
                    continue
                
                story.append(Paragraph(f"<b>{product_name}</b>", ParagraphStyle(
                    'ProductName', parent=body_style, fontSize=11, textColor=colors.HexColor('#004080'),
                    spaceBefore=6, spaceAfter=4
                )))
                
                # Bias and Confidence
                bias = product_data.get("bias", "Not provided")
                confidence = product_data.get("confidence_0_100")
                conf_text = f"{confidence}" if confidence is not None else "Not provided"
                story.append(Paragraph(f"Bias: {bias.capitalize()} | Confidence: {conf_text}/100", body_style))
                
                # Key Levels
                key_levels = product_data.get("key_levels", [])
                if key_levels:
                    levels_text = ", ".join(str(level) for level in key_levels)
                    story.append(Paragraph(f"<b>Key Levels:</b> {levels_text}", body_style))
                
                # Catalysts
                catalysts = product_data.get("catalysts", [])
                if catalysts:
                    cat_text = "; ".join(catalysts)
                    story.append(Paragraph(f"<b>Catalysts:</b> {cat_text}", body_style))
                
                # Risks
                risks = product_data.get("risks", [])
                if risks:
                    risks_text = "; ".join(risks)
                    story.append(Paragraph(f"<b>Risks:</b> {risks_text}", body_style))
                
                story.append(Spacer(1, 0.1*inch))
        elif products:
            # Just list products if no detailed data
            products_text = ", ".join(products)
            story.append(Paragraph(f"Products mentioned: {products_text}", body_style))
    
    # Footer
    story.append(Spacer(1, 0.3*inch))
    footer_text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    model = summary.get("meta", {}).get("model", "gpt-4o-mini") if isinstance(summary.get("meta"), dict) else "gpt-4o-mini"
    footer_text += f" | Model: {model}"
    story.append(Paragraph(f"<font size=7 color='gray'>{footer_text}</font>", body_style))
    
    # Build PDF
    doc.build(story)
    
    return output_path


def render_summary_pdf_from_pdf(pdf_path: Path) -> Optional[Path]:
    """
    Find corresponding __sum.json and generate PDF.
    
    Args:
        pdf_path: Path to original PDF file
    
    Returns:
        Path to generated PDF, or None if JSON doesn't exist
    """
    # Find corresponding JSON file
    json_path = pdf_path.parent / f"{pdf_path.stem}__sum.json"
    
    if not json_path.exists():
        return None
    
    # Generate PDF
    pdf_output = pdf_path.parent / f"{pdf_path.stem}__sum.pdf"
    return render_summary_pdf(json_path, pdf_output)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python summary_render.py <json_file> [output_pdf]")
        sys.exit(1)
    
    json_file = Path(sys.argv[1])
    output_file = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    
    try:
        result = render_summary_pdf(json_file, output_file)
        print(f"Generated: {result}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

