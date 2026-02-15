"""
Professional Trader-Focused PDF Summary Renderer

Purpose: Convert JSON summaries to clean, scannable, trader-notebook style PDFs
Author: Kevin Lefebvre
Last Updated: 2026-01-10

This module renders __sum.json files into professional PDF summaries designed for
beginner/intern-level traders. Focus on clarity, context, and "why it matters".
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple, List

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, PageBreak, 
        Table, TableStyle, KeepTogether
    )
    from reportlab.pdfgen import canvas
    from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False


# =========================
# STYLE CONFIGURATION
# =========================

# Background color (light tint)
BG_COLOR = colors.HexColor('#F8F9FA')  # Very light gray-blue

# Bias banner colors
BIAS_COLORS = {
    'bullish': colors.HexColor('#28A745'),    # Green
    'neutral': colors.HexColor('#FFC107'),    # Yellow
    'bearish': colors.HexColor('#DC3545'),    # Red
}

# Score badge colors (0-10 scale)
SCORE_COLORS = {
    'dark_red': colors.HexColor('#8B0000'),      # 0-2
    'orange_red': colors.HexColor('#FF4500'),    # 3-4
    'yellow': colors.HexColor('#FFD700'),        # 5
    'yellow_green': colors.HexColor('#9ACD32'),  # 6-7
    'green': colors.HexColor('#228B22'),         # 8-10
}

# Section divider color
DIVIDER_COLOR = colors.HexColor('#DEE2E6')

# Text colors
TITLE_COLOR = colors.HexColor('#0056B3')  # Blue for title
HEADER_COLOR = colors.HexColor('#0066CC')  # Lighter blue for section headers
BODY_COLOR = colors.HexColor('#212529')
MUTED_COLOR = colors.HexColor('#6C757D')
SUBHEADER_COLOR = colors.HexColor('#004085')  # Darker blue for product subheaders

# Actionable box highlight
ACTIONABLE_BG = colors.HexColor('#FFF3CD')  # Light yellow background
ACTIONABLE_BORDER = colors.HexColor('#FFC107')  # Yellow border


def get_score_color(score: int) -> colors.Color:
    """Get color for score badge (0-10 scale)."""
    if score <= 2:
        return SCORE_COLORS['dark_red']
    elif score <= 4:
        return SCORE_COLORS['orange_red']
    elif score == 5:
        return SCORE_COLORS['yellow']
    elif score <= 7:
        return SCORE_COLORS['yellow_green']
    else:  # 8-10
        return SCORE_COLORS['green']


def get_bias_color(bias: str) -> colors.Color:
    """Get color for bias banner."""
    bias_lower = bias.lower() if bias else 'neutral'
    return BIAS_COLORS.get(bias_lower, BIAS_COLORS['neutral'])


# Reason-specific messages for LOW CONFIDENCE banner (meta.low_confidence_reason)
LOW_CONFIDENCE_MESSAGES = {
    "degraded_extraction": (
        "This summary was generated from degraded text extraction. "
        "Content may be incomplete or less accurate than typical summaries."
    ),
    "unverified_numerics": (
        "Some numeric claims could not be verified against the source. "
        "Content may be incomplete or less accurate than typical summaries."
    ),
    "ocr_fallback": (
        "This summary was generated from OCR fallback. "
        "Text recognition may contain errors; content may be incomplete or less accurate."
    ),
}


def get_low_confidence_banner_message(meta: dict) -> str:
    """Return reason-specific banner message from meta.low_confidence_reason; default if unknown."""
    reason = (meta.get("low_confidence_reason") or "").strip()
    # Use first segment when reason is compound (e.g. "degraded_extraction; unverified_numerics")
    primary = reason.split(";")[0].strip().lower() if reason else ""
    return LOW_CONFIDENCE_MESSAGES.get(
        primary,
        "This summary was generated with low confidence. "
        "Content may be incomplete or less accurate than typical summaries.",
    )


def add_page_background_and_footer(canv, doc):
    """Callback to add background and footer to each page."""
    # Draw background
    canv.saveState()
    canv.setFillColor(BG_COLOR)
    canv.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
    canv.restoreState()
    
    # Draw footer
    canv.saveState()
    canv.setFont('Helvetica', 8)
    canv.setFillColor(MUTED_COLOR)
    
    # Generation timestamp (left)
    timestamp = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    canv.drawString(0.75*inch, 0.5*inch, timestamp)
    
    # Model info (right)
    model_info = f"Model: gpt-4o-mini"
    canv.drawRightString(letter[0] - 0.75*inch, 0.5*inch, model_info)
    
    canv.restoreState()


def create_score_badge_table(score: int) -> Table:
    """Create a circular score badge."""
    score_color = get_score_color(score)
    
    # Score text
    score_text = f"<font size=16 color=white><b>{score}/10</b></font>"
    
    badge_data = [[Paragraph(score_text, ParagraphStyle(
        'BadgeText',
        alignment=TA_CENTER,
        fontSize=16,
        textColor=colors.white
    ))]]
    
    badge = Table(badge_data, colWidths=[0.8*inch], rowHeights=[0.8*inch])
    badge.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), score_color),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [10, 10, 10, 10]),  # Rounded corners
    ]))
    
    return badge


# Standard pill height for all boxes (consistent across all pills)
PILL_HEIGHT = 0.4*inch

def create_metadata_pill_box(text: str, is_timeframe: bool = False) -> Table:
    """
    Create a pill box for metadata (provider, date, or timeframe).
    All pills use the same height for consistency.
    
    Args:
        text: Text to display in the pill
        is_timeframe: If True, use larger font and primary color (for timeframe pill)
    """
    if is_timeframe:
        # Timeframe pill: larger, higher contrast (primary blue)
        bg_color = colors.HexColor('#007BFF')  # Primary blue
        text_color = colors.white
        font_size = 11
        font_weight = 'Helvetica-Bold'
        padding = 6
    else:
        # Provider/Date pill: neutral gray
        bg_color = colors.HexColor('#E9ECEF')  # Neutral gray
        text_color = colors.HexColor('#495057')  # Dark gray text
        font_size = 9
        font_weight = 'Helvetica'
        padding = 4
    
    pill_text = Paragraph(text, ParagraphStyle(
        'PillText',
        alignment=TA_CENTER,
        fontSize=font_size,
        textColor=text_color,
        fontName=font_weight,
        leading=font_size + 2
    ))
    
    pill_data = [[pill_text]]
    
    # Estimate width based on text length (approximate)
    text_width = len(text) * (font_size * 0.6)  # Rough estimate
    pill_width = max(text_width + (padding * 2), 0.8*inch)
    
    pill = Table(pill_data, colWidths=[pill_width], rowHeights=[PILL_HEIGHT])
    pill.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bg_color),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),  # Rounded corners
        ('TOPPADDING', (0, 0), (-1, -1), padding / 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), padding / 2),
        ('LEFTPADDING', (0, 0), (-1, -1), padding),
        ('RIGHTPADDING', (0, 0), (-1, -1), padding),
    ]))
    
    return pill


def create_score_pill_box(score: int) -> Table:
    """
    Create a pill box for the score (similar style to other pills, same height).
    
    Args:
        score: Score value (0-10)
    """
    score_color = get_score_color(score)
    text_color = colors.white
    
    score_text = f"{score}/10"
    
    pill_text = Paragraph(score_text, ParagraphStyle(
        'ScorePillText',
        alignment=TA_CENTER,
        fontSize=11,
        textColor=text_color,
        fontName='Helvetica-Bold',
        leading=13
    ))
    
    pill_data = [[pill_text]]
    
    # Width for score pill (consistent with timeframe pill)
    pill_width = 0.9*inch
    
    pill = Table(pill_data, colWidths=[pill_width], rowHeights=[PILL_HEIGHT])
    pill.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), score_color),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [8, 8, 8, 8]),  # Rounded corners
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    return pill


def create_metadata_pills_row(provider: str, date_str: str, timeframe: str, score: int) -> Table:
    """
    Create a horizontal row of 4 pill boxes: [Provider] [Date] [Timeframe] [Score]
    
    Args:
        provider: Provider name (e.g., "MUFG")
        date_str: Date string in "Jan 09, 2026" format
        timeframe: Timeframe (e.g., "1–3D", "1–2W")
        score: Score value (0-10)
    """
    provider_pill = create_metadata_pill_box(provider, is_timeframe=False)
    date_pill = create_metadata_pill_box(date_str, is_timeframe=False)
    timeframe_pill = create_metadata_pill_box(timeframe, is_timeframe=True)
    score_pill = create_score_pill_box(score)
    
    # Create a horizontal table with 4 pills and spacing between them
    pills_row_data = [[provider_pill, date_pill, timeframe_pill, score_pill]]
    
    # Column widths: distribute space across 4 pills
    pills_row = Table(pills_row_data, colWidths=[1.4*inch, 1.6*inch, 1.3*inch, 1.0*inch])
    pills_row.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),      # Provider: left-aligned
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),    # Date: center-aligned
        ('ALIGN', (2, 0), (2, 0), 'LEFT'),      # Timeframe: left-aligned
        ('ALIGN', (3, 0), (3, 0), 'LEFT'),      # Score: left-aligned
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        # Small gaps between pills
        ('RIGHTPADDING', (0, 0), (0, 0), 0.08*inch),
        ('LEFTPADDING', (1, 0), (1, 0), 0.08*inch),
        ('RIGHTPADDING', (1, 0), (1, 0), 0.08*inch),
        ('LEFTPADDING', (2, 0), (2, 0), 0.08*inch),
        ('RIGHTPADDING', (2, 0), (2, 0), 0.08*inch),
        ('LEFTPADDING', (3, 0), (3, 0), 0.08*inch),
    ]))
    
    return pills_row


def create_bias_banner(bias: str) -> Table:
    """Create color-coded bias banner."""
    bias_text = f"Overall Bias: {bias.capitalize()}"
    bias_color = get_bias_color(bias)
    
    # Use white text for dark backgrounds, black for light
    text_color = colors.white if bias.lower() in ['bullish', 'bearish'] else colors.black
    
    banner_data = [[Paragraph(f"<b>{bias_text}</b>", ParagraphStyle(
        'BiasText',
        alignment=TA_CENTER,
        fontSize=12,
        textColor=text_color
    ))]] 
    
    banner = Table(banner_data, colWidths=[6.5*inch], rowHeights=[0.4*inch])
    banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), bias_color),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [5, 5, 5, 5]),
    ]))
    
    return banner


def create_theme_banner(theme: str) -> Table:
    """Create theme banner (for multi-product notes)."""
    theme_text = f"Theme: {theme}"
    
    # Use neutral color for theme banner (slight gray tint)
    banner_color = colors.HexColor('#E8E8E8')  # Light gray
    
    banner_data = [[Paragraph(f"<b>{theme_text}</b>", ParagraphStyle(
        'ThemeText',
        alignment=TA_CENTER,
        fontSize=12,
        textColor=colors.HexColor('#333333')
    ))]] 
    
    banner = Table(banner_data, colWidths=[6.5*inch], rowHeights=[0.4*inch])
    banner.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), banner_color),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [5, 5, 5, 5]),
    ]))
    
    return banner


def create_section_divider() -> Table:
    """Create subtle section divider."""
    divider = Table([['']], colWidths=[6.5*inch], rowHeights=[0.02*inch])
    divider.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), DIVIDER_COLOR),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    return divider

def create_rollup_pills_row(provider_text: str, date_text: str, timeframe_text: str) -> Table:
    """
    Create a horizontal row of 3 pill boxes for rollups: [Provider] [Date] [Timeframe]
    
    Args:
        provider_text: Provider name(s) (e.g., "GM, MUFG")
        date_text: Date string (e.g., "Jan 04, 2026" or date range for weekly)
        timeframe_text: Timeframe (e.g., "Daily", "Weekly")
    """
    provider_pill = create_metadata_pill_box(provider_text, is_timeframe=False)
    date_pill = create_metadata_pill_box(date_text, is_timeframe=False)
    timeframe_pill = create_metadata_pill_box(timeframe_text, is_timeframe=True)
    
    # Create a horizontal table with 3 pills and spacing between them
    pills_row_data = [[provider_pill, date_pill, timeframe_pill]]
    
    # Column widths: distribute space across 3 pills (adjust based on expected text lengths)
    pills_row = Table(pills_row_data, colWidths=[2.0*inch, 2.0*inch, 1.5*inch])
    pills_row.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),      # Provider: left-aligned
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),    # Date: center-aligned
        ('ALIGN', (2, 0), (2, 0), 'LEFT'),      # Timeframe: left-aligned
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        # Small gaps between pills
        ('RIGHTPADDING', (0, 0), (0, 0), 0.08*inch),
        ('LEFTPADDING', (1, 0), (1, 0), 0.08*inch),
        ('RIGHTPADDING', (1, 0), (1, 0), 0.08*inch),
        ('LEFTPADDING', (2, 0), (2, 0), 0.08*inch),
    ]))
    
    return pills_row

def create_small_chip_pill(text: str) -> Table:
    """Create a small pill box for products/sources chips."""
    pill_text = Paragraph(text, ParagraphStyle(
        'ChipText',
        alignment=TA_CENTER,
        fontSize=8,
        textColor=colors.HexColor('#495057'),
        fontName='Helvetica',
        leading=10
    ))
    
    pill_data = [[pill_text]]
    
    # Estimate width based on text length
    text_width = len(text) * (8 * 0.5)
    pill_width = max(text_width + 8, 0.5*inch)
    
    pill = Table(pill_data, colWidths=[pill_width], rowHeights=[0.25*inch])
    pill.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#E9ECEF')),  # Light gray
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROUNDEDCORNERS', [6, 6, 6, 6]),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]))
    
    return pill

def create_chips_row_simple(chip_texts: List[str], label: str = "") -> Optional[Paragraph]:
    """
    Create a simple paragraph with chips text (for products/sources).
    Uses styled text rather than individual pill boxes for simplicity.
    
    Args:
        chip_texts: List of text for each chip
        label: Optional label text (e.g., "Products:", "Sources:")
    """
    if not chip_texts:
        return None
    
    # Limit to 20 chips for display
    display_texts = chip_texts[:20]
    chips_text = " • ".join(display_texts)
    
    if label:
        full_text = f"<b>{label}</b> {chips_text}"
    else:
        full_text = chips_text
    
    chip_style = ParagraphStyle(
        'ChipRow',
        fontSize=9,
        textColor=MUTED_COLOR,
        fontName='Helvetica',
        leading=12,
        spaceAfter=4
    )
    
    return Paragraph(full_text, chip_style)


def _render_failed_summary_pdf(output_path: Path, summary: dict) -> bool:
    """
    Render a clear failure page for failed extractions.
    
    Args:
        output_path: Path to output PDF
        summary: Summary JSON with failed extraction status
    
    Returns:
        True if successful, False otherwise
    """
    if not REPORTLAB_AVAILABLE:
        return False
    
    try:
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=inch,
            leftMargin=inch,
            topMargin=inch,
            bottomMargin=inch
        )
        
        story = []
        styles = getSampleStyleSheet()
        
        # Title
        meta = summary.get("meta", {})
        title = meta.get("title", "Unknown Document")
        extraction = summary.get("extraction", {})
        reason = extraction.get("reason", "unknown error")
        
        # Title style
        title_style = ParagraphStyle(
            'FailedTitle',
            parent=styles['Title'],
            fontSize=18,
            textColor=colors.HexColor('#DC3545'),  # Red
            spaceAfter=12,
            alignment=TA_CENTER
        )
        
        # Subtitle style
        subtitle_style = ParagraphStyle(
            'FailedSubtitle',
            parent=styles['Normal'],
            fontSize=14,
            textColor=colors.HexColor('#6C757D'),
            spaceAfter=24,
            alignment=TA_CENTER
        )
        
        # Body style
        body_style = ParagraphStyle(
            'FailedBody',
            parent=styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#212529'),
            spaceAfter=12,
            leftIndent=20
        )
        
        # Add content
        story.append(Paragraph("SUMMARY UNAVAILABLE", title_style))
        story.append(Spacer(1, 0.2*inch))
        story.append(Paragraph(f"Document: {title}", subtitle_style))
        story.append(Spacer(1, 0.3*inch))
        
        # Error box
        error_data = [[Paragraph(f"<b>Extraction Status:</b> FAILED", body_style)],
                      [Paragraph(f"<b>Reason:</b> {reason}", body_style)]]
        
        error_table = Table(error_data, colWidths=[5.5*inch])
        error_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFF3CD')),
            ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#FFC107')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('LEFTPADDING', (0, 0), (-1, -1), 12),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ('TOPPADDING', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
        ]))
        
        story.append(error_table)
        story.append(Spacer(1, 0.4*inch))
        
        # Explanation
        story.append(Paragraph("<b>This document could not be processed.</b>", body_style))
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph("Possible causes:", body_style))
        story.append(Paragraph("• Image-only PDF requiring OCR", body_style))
        story.append(Paragraph("• Low-quality text extraction", body_style))
        story.append(Paragraph("• Templated/low-information LLM output", body_style))
        story.append(Paragraph("• Insufficient readable text content", body_style))
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph("<b>No summary will be generated for this document.</b>", body_style))
        
        # Build PDF
        doc.build(story)
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to render failure PDF: {e}")
        return False


def render_summary_pdf(json_path: Path, output_path: Optional[Path] = None) -> bool:
    """
    Generate professional trader-focused PDF from JSON summary.
    
    Args:
        json_path: Path to __sum.json file
        output_path: Optional output path (defaults to <stem>__sum.pdf)
    
    Returns:
        True if successful, False otherwise
    """
    if not REPORTLAB_AVAILABLE:
        print("[ERROR] reportlab is required. Install with: pip install reportlab")
        return False
    
    if not json_path.exists():
        print(f"[ERROR] JSON file not found: {json_path}")
        return False
    
    # Load JSON
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            summary = json.load(f)
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in {json_path}: {e}")
        return False
    
    # Check if this is a rollup (different schema)
    schema_version = summary.get("schema_version", "")
    kind = summary.get("kind", "")
    if schema_version == "twifo.rollup.v1" or kind in ("rollup_daily", "rollup_weekly"):
        # Determine output path for rollup
        if output_path is None:
            output_path = json_path.parent / f"{json_path.stem}.pdf"
        return render_rollup_pdf(json_path, output_path, summary)
    
    # Determine output path
    if output_path is None:
        output_path = json_path.parent / f"{json_path.stem}.pdf"
    
    # Check if extraction failed - render failure page instead
    # Allow "ok" and "degraded" (degraded gets a warning banner but still renders)
    extraction = summary.get("extraction", {})
    extraction_status = extraction.get("status", "unknown")
    if extraction_status not in ("ok", "degraded"):
        return _render_failed_summary_pdf(output_path, summary)
    
    try:
        # Create PDF
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=1*inch
        )
        
        story = []
        
        # =========================
        # EGYPT-FORMAT HEADER
        # =========================
        
        meta = summary.get("meta", {})
        provider = meta.get("provider", "O")
        date_str = meta.get("published_date", "")
        horizon = meta.get("horizon", "u")
        theme = meta.get("theme", "")
        products = meta.get("products", [])
        
        # Fix provider if still a short code or "O" — extract from title prefix
        if provider in ("O", "Unknown", "") or len(provider) <= 3:
            raw_title = meta.get("title", "")
            if "_" in raw_title:
                code = raw_title.split("_", 1)[0]
                _pmap = {
                    "BOA": "Bank of America", "BA": "Barclays", "BR": "BlackRock",
                    "DB": "Deutsche Bank", "GM": "Goldman Sachs", "HT": "HighTower Research",
                    "JPM": "JP Morgan", "MZ": "Mizuho", "TSL": "TSLombard", "WF": "Wells Fargo",
                    "SEB": "SEB Commodities", "R": "Rabobank", "MUFG": "MUFG", "ANZ": "ANZ",
                    "BCA": "BCA", "BNPP": "BNPP", "BNY": "Bank of New York Melon",
                    "CACIB": "CACIB", "CITI": "Citi", "HSBC": "HSBC", "ING": "ING",
                    "MS": "Morgan Stanley", "NOM": "Nomura", "RBC": "RBC", "SG": "SocGen",
                    "STI": "Stifel", "TME": "TME", "UBS": "UBS",
                }
                mapped = _pmap.get(code)
                if mapped:
                    provider = mapped
        model = meta.get("model", "gpt-4o-mini")
        generated_at = meta.get("generated_at_iso", "")
        
        # Get score
        score = summary.get("summary_score_0_10", 0)
        if score == 0:
            if "self_evaluation" in summary:
                score = summary["self_evaluation"].get("summary_score_0_10", 0)
            elif "scan" in summary:
                score = summary["scan"].get("score", {}).get("summary_score_0_10", 0)
        
        # Format date
        try:
            if len(date_str) == 8:
                dt_obj = datetime.strptime(date_str, "%Y%m%d")
                date_display = dt_obj.strftime("%b %d, %Y")
            else:
                date_display = date_str
        except:
            date_display = date_str
        
        # Format horizon
        horizon_map = {
            "d": "0–3D",
            "w": "1–2W",
            "m": ">2W",
            "q": ">2W",
            "y": ">2W",
            "u": "1–2W"
        }
        horizon_display = horizon_map.get(horizon.lower(), horizon)
        
        # Title (from metadata, fallback to cleaned filename)
        title_text = meta.get("title", "")
        if not title_text:
            original_name = json_path.stem.replace('__sum', '')
            title_text = original_name.replace('_', ' ').replace('  ', ' ')
        
        title_style = ParagraphStyle(
            'Title',
            fontSize=14,
            fontName='Helvetica-Bold',
            textColor=TITLE_COLOR,
            spaceAfter=4,
            leading=17
        )
        story.append(Paragraph(title_text, title_style))
        
        # Header line: PROVIDER  DATE  HORIZON  SCORE/10
        header_line = f"{provider}  {date_display}  {horizon_display}  {score}/10"
        header_style = ParagraphStyle(
            'Header',
            fontSize=11,
            fontName='Helvetica',
            textColor=BODY_COLOR,
            spaceAfter=6,
            leading=14
        )
        story.append(Paragraph(header_line, header_style))
        
        # Theme line
        if theme:
            theme_text = f"<b>Theme:</b> {theme}"
            theme_style = ParagraphStyle(
                'Theme',
                fontSize=10,
                textColor=BODY_COLOR,
                spaceAfter=4,
                leading=13
            )
            story.append(Paragraph(theme_text, theme_style))
        
        # Products line
        if products:
            products_text = f"<b>Products:</b> {', '.join(products)}"
            products_style = ParagraphStyle(
                'Products',
                fontSize=10,
                textColor=BODY_COLOR,
                spaceAfter=10,
                leading=13
            )
            story.append(Paragraph(products_text, products_style))
        
        story.append(Spacer(1, 0.1*inch))
        
        # Warning banner for degraded/low-confidence extractions
        is_low_confidence = meta.get("low_confidence", False)
        extraction_status = extraction.get("status", "ok")
        
        if is_low_confidence or extraction_status == "degraded":
            banner_msg = get_low_confidence_banner_message(meta)
            warning_data = [[
                Paragraph(
                    "<b>⚠️ LOW CONFIDENCE</b><br/>" + banner_msg,
                    ParagraphStyle(
                        'WarningText',
                        fontSize=9,
                        textColor=colors.HexColor('#856404'),
                        alignment=TA_LEFT,
                        leading=11
                    )
                )
            ]]
            
            warning_table = Table(warning_data, colWidths=[6.5*inch])
            warning_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFF3CD')),
                ('BOX', (0, 0), (-1, -1), 2, colors.HexColor('#FFC107')),
                ('LEFTPADDING', (0, 0), (-1, -1), 10),
                ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ]))
            
            story.append(Spacer(1, 0.1*inch))
            story.append(warning_table)
            story.append(Spacer(1, 0.15*inch))
        
        # =========================
        # EGYPT-FORMAT BODY SECTIONS
        # =========================
        
        # Define reusable styles
        section_header_style = ParagraphStyle(
            'SectionHeader',
            fontSize=12,
            fontName='Helvetica-Bold',
            textColor=HEADER_COLOR,
            spaceBefore=8,
            spaceAfter=6,
            leading=15
        )
        
        bullet_style = ParagraphStyle(
            'Bullet',
            fontSize=10,
            textColor=BODY_COLOR,
            leftIndent=15,
            bulletIndent=0,
            leading=14,
            spaceAfter=3
        )
        
        # Extract content (handle both new twifo.sum.v1 and old schemas)
        sections = summary.get("sections", {})
        core_summary = summary.get("core_summary", {})
        scan = summary.get("scan", {})
        
        # Try new schema first (twifo.sum.v1), then fall back to old schemas
        if sections:
            # New schema: sections.tldr, sections.what_occurred, etc.
            tldr = sections.get("tldr", [])
            actionable = sections.get("what_occurred", [])
            forward_watchlist = sections.get("forward_watch", [])
            tips_and_reminders = sections.get("tips_reminders", [])
            past_context = []  # Not present in new schema
        else:
            # Old schemas
            tldr = core_summary.get("tldr", []) or scan.get("tldr", [])
            actionable = core_summary.get("actionable", []) or scan.get("top_actionables", [])
            tips_and_reminders = core_summary.get("tips_and_reminders", []) or scan.get("tips_and_reminders", [])
            
            # Time separation
            time_sep = summary.get("time_separation", {}) or summary.get("deep_dive", {}).get("time_separation", {})
            past_context = time_sep.get("past_context", [])
            forward_watchlist = time_sep.get("forward_watchlist", [])
        
        # Per-product data
        per_product = summary.get("per_product", {})
        
        # =========================
        # 📌 TLDR SECTION
        # =========================
        if tldr:
            story.append(create_section_divider())
            story.append(Spacer(1, 0.1*inch))
            story.append(Paragraph("📌 TL;DR", section_header_style))
            
            for item in tldr:
                # Handle both string and dict formats
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                if text:
                    story.append(Paragraph(f"• {text}", bullet_style))
            
            story.append(Spacer(1, 0.15*inch))
        
        # =========================
        # KEY DATA / CONTEXT
        # =========================
        key_data = sections.get("what_occurred", []) if sections else []
        if key_data:
            story.append(Paragraph("KEY DATA / CONTEXT", section_header_style))
            
            for item in key_data:
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                if text:
                    story.append(Paragraph(f"• {text}", bullet_style))
            
            story.append(Spacer(1, 0.1*inch))
        
        # =========================
        # FORWARD WATCH / EXPECTATIONS
        # =========================
        if forward_watchlist:
            story.append(Paragraph("FORWARD WATCH / EXPECTATIONS", section_header_style))
            
            for item in forward_watchlist:
                # Handle both string and dict formats
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                if text:
                    story.append(Paragraph(f"• {text}", bullet_style))
            
            story.append(Spacer(1, 0.1*inch))
        
        # Generated line (before ACTIONABLE)
        gen_display = generated_at.split("T")[0] if "T" in generated_at else generated_at
        gen_text = f"Generated: {gen_display}  Model: {model}"
        gen_style = ParagraphStyle(
            'Generated',
            fontSize=9,
            textColor=MUTED_COLOR,
            spaceAfter=8,
            leading=12
        )
        story.append(Paragraph(gen_text, gen_style))
        
        # =========================
        # ACTIONABLE
        # =========================
        trade_ideas = sections.get("trade_ideas", []) if sections else []
        if trade_ideas:
            story.append(Paragraph("ACTIONABLE", section_header_style))
            
            for item in trade_ideas:
                text = item.get("text", "") if isinstance(item, dict) else str(item)
                if text:
                    story.append(Paragraph(f"• {text}", bullet_style))
            
            story.append(Spacer(1, 0.1*inch))
        
        # =========================
        # TIPS & REMINDERS
        # =========================
        if tips_and_reminders:
            story.append(Paragraph("TIPS & REMINDERS", section_header_style))
            
            for tip in tips_and_reminders:
                text = tip.get("text", "") if isinstance(tip, dict) else str(tip)
                if text:
                    story.append(Paragraph(f"• {text}", bullet_style))
            
            story.append(Spacer(1, 0.1*inch))
        
        # =========================
        # CHART OBSERVATIONS (v1.2)
        # =========================
        chart_observations = summary.get("chart_observations", [])
        chart_score_val = summary.get("chart_score_0_3", 0)
        if chart_observations and chart_score_val > 0:
            story.append(Paragraph(f"CHART OBSERVATIONS (chart score: {chart_score_val}/3)", section_header_style))
            
            for obs in chart_observations:
                text = obs.get("text", "") if isinstance(obs, dict) else str(obs)
                if text:
                    story.append(Paragraph(f"• {text}", bullet_style))
            
            story.append(Spacer(1, 0.1*inch))
        
        # =========================
        # FINGERPRINT QUOTES (v1.2)
        # =========================
        fingerprint_quotes = summary.get("fingerprint_quotes", [])
        if fingerprint_quotes:
            fp_style = ParagraphStyle(
                'FingerprintQuote',
                fontSize=8,
                textColor=colors.HexColor('#666666'),
                fontName='Helvetica-Oblique',
                leftIndent=12,
                spaceAfter=3,
                leading=10
            )
            fp_header_style = ParagraphStyle(
                'FingerprintHeader',
                fontSize=8,
                textColor=colors.HexColor('#999999'),
                fontName='Helvetica',
                spaceAfter=4,
                spaceBefore=8,
                leading=10
            )
            story.append(Paragraph("SOURCE FINGERPRINTS", fp_header_style))
            for quote in fingerprint_quotes:
                if isinstance(quote, str) and quote.strip():
                    escaped = quote.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    story.append(Paragraph(f'"{escaped}"', fp_style))
            
            story.append(Spacer(1, 0.1*inch))
        
        # Build PDF with callbacks for background and footer
        doc.build(story, onFirstPage=add_page_background_and_footer, onLaterPages=add_page_background_and_footer)
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to generate PDF: {e}")
        import traceback
        traceback.print_exc()
        return False


def render_rollup_pdf(json_path: Path, output_path: Optional[Path], rollup: dict) -> bool:
    """
    Generate PDF from rollup JSON (daily or weekly), organized by product categories.
    
    Args:
        json_path: Path to rollup JSON file
        output_path: Output path for PDF
        rollup: Already-loaded rollup dictionary
    
    Returns:
        True if successful, False otherwise
    """
    if not REPORTLAB_AVAILABLE:
        print("[ERROR] reportlab is required. Install with: pip install reportlab")
        return False
    
    try:
        # Create PDF
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=0.75*inch,
            leftMargin=0.75*inch,
            topMargin=0.75*inch,
            bottomMargin=1*inch
        )
        
        story = []
        styles = getSampleStyleSheet()
        
        # =========================
        # HEADER SECTION
        # =========================
        ui = rollup.get("ui", {})
        sections = rollup.get("sections", {})
        
        # Title - centered with professional font
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=28,
            textColor=TITLE_COLOR,
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        story.append(Paragraph(ui.get("title", "Daily Recap"), title_style))
        story.append(Spacer(1, 0.15*inch))
        
        # Header pills (Providers, Date, Timeframe) - removed for both daily and weekly
        meta = rollup.get("meta", {})
        rollup_kind = meta.get("rollup_kind", "daily")
        # No pills for daily or weekly rollups as per user request
        
        # Chips rows (Products, Sources) - use styled text
        chips_rows = ui.get("chips_rows", [])
        if chips_rows:
            # Row 1: Products
            if len(chips_rows) > 0:
                row1_chips = chips_rows[0]
                row1_texts = [chip.get("text", "") for chip in row1_chips[:20]]  # Limit display
                if row1_texts:
                    products_para = create_chips_row_simple(row1_texts, label="Products:")
                    if products_para:
                        story.append(products_para)
            
            # Row 2: Sources
            if len(chips_rows) > 1:
                row2_chips = chips_rows[1]
                row2_texts = [chip.get("text", "") for chip in row2_chips]
                if row2_texts:
                    sources_para = create_chips_row_simple(row2_texts, label="Sources:")
                    if sources_para:
                        story.append(sources_para)
        
        story.append(Spacer(1, 0.2*inch))
        story.append(create_section_divider())
        story.append(Spacer(1, 0.2*inch))
        
        # =========================
        # NEW ROLLUP SCHEMA SECTIONS (flat structure)
        # =========================
        
        # Define styles
        section_header_style = ParagraphStyle(
            'SectionHeader',
            parent=styles['Heading2'],
            fontSize=18,
            textColor=HEADER_COLOR,
            spaceAfter=12,
            spaceBefore=12,
            fontName='Helvetica-Bold'
        )
        
        subheader_style = ParagraphStyle(
            'SubHeader',
            parent=styles['Heading3'],
            fontSize=14,
            textColor=HEADER_COLOR,
            spaceAfter=8,
            spaceBefore=8,
            fontName='Helvetica-Bold'
        )
        
        bullet_style = ParagraphStyle(
            'Bullet',
            parent=styles['Normal'],
            fontSize=11,
            textColor=BODY_COLOR,
            leftIndent=12,
            leading=14,
            spaceAfter=6
        )
        
        # Check if this is new schema (has flat sections) or old schema (has by_category)
        by_category = sections.get("by_category", {})
        has_new_schema = not by_category and (
            sections.get("tldr") is not None or 
            sections.get("observations") is not None or
            sections.get("trade_ideas") is not None
        )
        
        if has_new_schema:
            # =========================
            # TLDR
            # =========================
            tldr_items = sections.get("tldr", [])
            if tldr_items:
                story.append(Paragraph("📋 TLDR", section_header_style))
                for item in tldr_items:
                    text = item.get("text", "") if isinstance(item, dict) else str(item)
                    sources = item.get("sources", []) if isinstance(item, dict) else []
                    sources_str = f" <i>({', '.join(sources)})</i>" if len(sources) > 1 else ""
                    story.append(Paragraph(f"• {text}{sources_str}", bullet_style))
                story.append(Spacer(1, 0.15*inch))
            
            # =========================
            # OBSERVATIONS (grouped by product)
            # =========================
            observations = sections.get("observations", {})
            if observations and isinstance(observations, dict):
                story.append(create_section_divider())
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph("What Occurred", section_header_style))
                
                # Sort products alphabetically, put General last
                sorted_products = sorted([p for p in observations.keys() if p != "General" and p != "Other"])
                if "General" in observations:
                    sorted_products.append("General")
                elif "Other" in observations:
                    sorted_products.append("Other")
                
                for product in sorted_products:
                    items = observations.get(product, [])
                    if items:
                        # KeepTogether for each product group (subheader + bullets) to avoid orphaned titles
                        product_group = []
                        product_group.append(Paragraph(f"<b>{product}</b>", subheader_style))
                        for item in items:
                            text = item.get("text", "") if isinstance(item, dict) else str(item)
                            sources = item.get("sources", []) if isinstance(item, dict) else []
                            
                            # Only show sources if > 1 (no product parentheses - product is already the header)
                            sources_str = f" <i>({', '.join(sources)})</i>" if len(sources) > 1 else ""
                            product_group.append(Paragraph(f"• {text}{sources_str}", bullet_style))
                        product_group.append(Spacer(1, 0.05*inch))
                        story.append(KeepTogether(product_group))
                story.append(Spacer(1, 0.15*inch))
            elif observations and isinstance(observations, list):
                # Fallback for old format (list)
                story.append(create_section_divider())
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph("What Occurred", section_header_style))
                for item in observations:
                    text = item.get("text", "") if isinstance(item, dict) else str(item)
                    sources = item.get("sources", []) if isinstance(item, dict) else []
                    sources_str = f" <i>({', '.join(sources)})</i>" if len(sources) > 1 else ""
                    story.append(Paragraph(f"• {text}{sources_str}", bullet_style))
                story.append(Spacer(1, 0.15*inch))
            
            # =========================
            # TRADE IDEAS (only show if any sections have content)
            # =========================
            trade_ideas = sections.get("trade_ideas", {})
            if trade_ideas and isinstance(trade_ideas, dict):
                d_1_3 = trade_ideas.get("d_1_3", [])
                w_1_2 = trade_ideas.get("w_1_2", [])
                gt_2w = trade_ideas.get("gt_2w", [])
                watchlist_only = trade_ideas.get("watchlist_only", [])
                
                # Only render Trade Ideas section if at least one bucket has content
                if d_1_3 or w_1_2 or gt_2w or watchlist_only:
                    story.append(create_section_divider())
                    story.append(Spacer(1, 0.1*inch))
                    story.append(Paragraph("💡 TRADE IDEAS", section_header_style))
                    
                    # 1-3 Day
                    if d_1_3:
                        # KeepTogether for timeframe subheader + its trade ideas
                        timeframe_group = []
                        timeframe_group.append(Paragraph("<b>1-3 Day (Tactical)</b>", subheader_style))
                        for idea in d_1_3:
                            direction = idea.get("direction", "").upper()
                            instrument = idea.get("instrument", "")
                            trigger = idea.get("trigger", "")
                            invalidation = idea.get("invalidation", "")
                            rationale = idea.get("rationale", "")
                            sources_list = idea.get("sources", [])
                            confidence = idea.get("confidence_0_100", 0)
                            
                            timeframe_group.append(Paragraph(f"• <b>{direction} {instrument}</b>", bullet_style))
                            if trigger:
                                timeframe_group.append(Paragraph(f"  <i>Trigger:</i> {trigger}", bullet_style))
                            if invalidation:
                                timeframe_group.append(Paragraph(f"  <i>Invalidation:</i> {invalidation}", bullet_style))
                            if rationale:
                                timeframe_group.append(Paragraph(f"  {rationale}", bullet_style))
                            if sources_list:
                                timeframe_group.append(Paragraph(f"  <i>Sources:</i> {', '.join(sources_list)}", bullet_style))
                            if confidence:
                                timeframe_group.append(Paragraph(f"  <i>Confidence:</i> {confidence}%", bullet_style))
                            timeframe_group.append(Spacer(1, 0.05*inch))
                        story.append(KeepTogether(timeframe_group))
                    
                    # 1-2 Week
                    if w_1_2:
                        timeframe_group = []
                        timeframe_group.append(Paragraph("<b>1-2 Week (Swing)</b>", subheader_style))
                        for idea in w_1_2:
                            direction = idea.get("direction", "").upper()
                            instrument = idea.get("instrument", "")
                            trigger = idea.get("trigger", "")
                            invalidation = idea.get("invalidation", "")
                            rationale = idea.get("rationale", "")
                            sources_list = idea.get("sources", [])
                            confidence = idea.get("confidence_0_100", 0)
                            
                            timeframe_group.append(Paragraph(f"• <b>{direction} {instrument}</b>", bullet_style))
                            if trigger:
                                timeframe_group.append(Paragraph(f"  <i>Trigger:</i> {trigger}", bullet_style))
                            if invalidation:
                                timeframe_group.append(Paragraph(f"  <i>Invalidation:</i> {invalidation}", bullet_style))
                            if rationale:
                                timeframe_group.append(Paragraph(f"  {rationale}", bullet_style))
                            if sources_list:
                                timeframe_group.append(Paragraph(f"  <i>Sources:</i> {', '.join(sources_list)}", bullet_style))
                            if confidence:
                                timeframe_group.append(Paragraph(f"  <i>Confidence:</i> {confidence}%", bullet_style))
                            timeframe_group.append(Spacer(1, 0.05*inch))
                        story.append(KeepTogether(timeframe_group))
                    
                    # >2 Week
                    if gt_2w:
                        timeframe_group = []
                        timeframe_group.append(Paragraph("<b>>2 Week (Position)</b>", subheader_style))
                        for idea in gt_2w:
                            direction = idea.get("direction", "").upper()
                            instrument = idea.get("instrument", "")
                            trigger = idea.get("trigger", "")
                            invalidation = idea.get("invalidation", "")
                            rationale = idea.get("rationale", "")
                            sources_list = idea.get("sources", [])
                            confidence = idea.get("confidence_0_100", 0)
                            
                            timeframe_group.append(Paragraph(f"• <b>{direction} {instrument}</b>", bullet_style))
                            if trigger:
                                timeframe_group.append(Paragraph(f"  <i>Trigger:</i> {trigger}", bullet_style))
                            if invalidation:
                                timeframe_group.append(Paragraph(f"  <i>Invalidation:</i> {invalidation}", bullet_style))
                            if rationale:
                                timeframe_group.append(Paragraph(f"  {rationale}", bullet_style))
                            if sources_list:
                                timeframe_group.append(Paragraph(f"  <i>Sources:</i> {', '.join(sources_list)}", bullet_style))
                            if confidence:
                                timeframe_group.append(Paragraph(f"  <i>Confidence:</i> {confidence}%", bullet_style))
                            timeframe_group.append(Spacer(1, 0.05*inch))
                        story.append(KeepTogether(timeframe_group))
                    
                    # Watchlist Only
                    if watchlist_only:
                        timeframe_group = []
                        timeframe_group.append(Paragraph("<b>Watchlist Only</b>", subheader_style))
                        for idea in watchlist_only:
                            direction = idea.get("direction", "").upper()
                            instrument = idea.get("instrument", "")
                            trigger = idea.get("trigger", "")
                            rationale = idea.get("rationale", "")
                            sources_list = idea.get("sources", [])
                            
                            timeframe_group.append(Paragraph(f"• <b>{direction} {instrument}</b>", bullet_style))
                            if trigger:
                                timeframe_group.append(Paragraph(f"  <i>Trigger:</i> {trigger}", bullet_style))
                            if rationale:
                                timeframe_group.append(Paragraph(f"  {rationale}", bullet_style))
                            if sources_list:
                                timeframe_group.append(Paragraph(f"  <i>Sources:</i> {', '.join(sources_list)}", bullet_style))
                            timeframe_group.append(Spacer(1, 0.05*inch))
                        story.append(KeepTogether(timeframe_group))
                    
                    story.append(Spacer(1, 0.15*inch))
            
            # =========================
            # FORWARD WATCH (grouped by product) - KeepTogether to avoid page breaks
            # =========================
            forward_watch = sections.get("forward_watch", {})
            if forward_watch and isinstance(forward_watch, dict):
                story.append(create_section_divider())
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph("🔭 Forward Watch", section_header_style))
                
                # Sort products alphabetically, put General last
                sorted_products = sorted([p for p in forward_watch.keys() if p != "General" and p != "Other"])
                if "General" in forward_watch:
                    sorted_products.append("General")
                elif "Other" in forward_watch:
                    sorted_products.append("Other")
                
                for product in sorted_products:
                    items = forward_watch.get(product, [])
                    if items:
                        # KeepTogether for each product group (subheader + bullets) to avoid orphaned titles
                        product_group = []
                        product_group.append(Paragraph(f"<b>{product}</b>", subheader_style))
                        for item in items:
                            text = item.get("text", "") if isinstance(item, dict) else str(item)
                            sources = item.get("sources", []) if isinstance(item, dict) else []
                            
                            # Only show sources if > 1 (no product parentheses - product is already the header)
                            sources_str = f" <i>({', '.join(sources)})</i>" if len(sources) > 1 else ""
                            product_group.append(Paragraph(f"• {text}{sources_str}", bullet_style))
                        product_group.append(Spacer(1, 0.05*inch))
                        story.append(KeepTogether(product_group))
                story.append(Spacer(1, 0.15*inch))
            elif forward_watch and isinstance(forward_watch, list):
                # Fallback for old format (list)
                story.append(create_section_divider())
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph("🔭 Forward Watch", section_header_style))
                for item in forward_watch:
                    text = item.get("text", "") if isinstance(item, dict) else str(item)
                    sources = item.get("sources", []) if isinstance(item, dict) else []
                    sources_str = f" <i>({', '.join(sources)})</i>" if len(sources) > 1 else ""
                    story.append(Paragraph(f"• {text}{sources_str}", bullet_style))
                story.append(Spacer(1, 0.15*inch))
            
            # =========================
            # WARNINGS
            # =========================
            warnings = sections.get("warnings", [])
            if warnings:
                story.append(create_section_divider())
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph("⚠️ WARNINGS", section_header_style))
                for item in warnings:
                    text = item.get("text", "") if isinstance(item, dict) else str(item)
                    sources = item.get("sources", []) if isinstance(item, dict) else []
                    sources_str = f" <i>({', '.join(sources)})</i>" if len(sources) > 1 else ""
                    story.append(Paragraph(f"• {text}{sources_str}", bullet_style))
                story.append(Spacer(1, 0.15*inch))
            
            # =========================
            # TIPS & REMINDERS
            # =========================
            tips = sections.get("tips_reminders", [])
            if tips:
                story.append(create_section_divider())
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph("💡 TIPS & REMINDERS", section_header_style))
                for item in tips:
                    text = item.get("text", "") if isinstance(item, dict) else str(item)
                    sources = item.get("sources", []) if isinstance(item, dict) else []
                    sources_str = f" <i>({', '.join(sources)})</i>" if len(sources) > 1 else ""
                    story.append(Paragraph(f"• {text}{sources_str}", bullet_style))
                story.append(Spacer(1, 0.15*inch))
            
            # =========================
            # CROSS-ASSET IMPACTS
            # =========================
            cross_asset = sections.get("cross_asset_impacts", [])
            if cross_asset:
                story.append(create_section_divider())
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph("🔗 CROSS-ASSET IMPACTS", section_header_style))
                for item in cross_asset:
                    text = item.get("text", "") if isinstance(item, dict) else str(item)
                    sources = item.get("sources", []) if isinstance(item, dict) else []
                    sources_str = f" <i>({', '.join(sources)})</i>" if len(sources) > 1 else ""
                    story.append(Paragraph(f"• {text}{sources_str}", bullet_style))
                story.append(Spacer(1, 0.15*inch))
            
            # =========================
            # SCENARIOS
            # =========================
            scenarios = sections.get("scenarios", [])
            if scenarios:
                story.append(create_section_divider())
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph("🎯 SCENARIOS", section_header_style))
                for item in scenarios:
                    text = item.get("text", "") if isinstance(item, dict) else str(item)
                    sources = item.get("sources", []) if isinstance(item, dict) else []
                    sources_str = f" <i>({', '.join(sources)})</i>" if len(sources) > 1 else ""
                    story.append(Paragraph(f"• {text}{sources_str}", bullet_style))
                story.append(Spacer(1, 0.15*inch))
        
        elif by_category:
            # Fallback: OLD SCHEMA with by_category (keep existing logic for backward compatibility)
            header_style = section_header_style
            for category in sorted(by_category.keys()):
                category_data = by_category[category]
                story.append(Paragraph(category.upper(), header_style))
                
                obs = category_data.get("observations", [])
                if obs:
                    story.append(Paragraph("What Occurred", subheader_style))
                    for item in obs:
                        text = item.get("text", "")
                        sources = item.get("sources", [])
                        sources_str = f" <i>({', '.join(sources)})</i>" if sources else ""
                        story.append(Paragraph(f"• {text}{sources_str}", bullet_style))
                    story.append(Spacer(1, 0.1*inch))
                
                story.append(create_section_divider())
                story.append(Spacer(1, 0.2*inch))
        
        # Build PDF
        doc.build(story, onFirstPage=add_page_background_and_footer, onLaterPages=add_page_background_and_footer)
        
        print(f"[OK] Rollup PDF created: {output_path.name}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to generate rollup PDF: {e}")
        import traceback
        traceback.print_exc()
        return False
