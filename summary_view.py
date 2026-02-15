"""
Summary View Renderer for TWIFO App
Purpose: Beautiful article rendering from sum.json
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

import json
from pathlib import Path
from typing import Optional, Dict, Any
from dash import html, dcc


def load_summary_json(basename: str, files_dir: Path, path_manager=None) -> Optional[Dict[str, Any]]:
    """
    Load sum.json for a given basename.
    
    Args:
        basename: Base filename without extension (e.g., "20260212__BOA__report__abc123")
        files_dir: Root directory
        path_manager: TWIFOPathManager instance (if available)
    
    Returns:
        Parsed JSON dict or None if not found
    """
    try:
        if path_manager:
            # New layout: artifacts/<basename>/sum.json
            sum_path = path_manager.artifact_path(basename, 'sum.json')
        else:
            # Legacy layout: root/<basename>__sum.json
            sum_path = files_dir / f"{basename}__sum.json"
        
        if not sum_path.exists():
            return None
        
        with open(sum_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    except Exception as e:
        print(f"[ERROR] Failed to load summary for {basename}: {e}")
        return None


def is_stub_summary(sum_json: Dict[str, Any]) -> bool:
    """Check if summary is a stub/failed."""
    if sum_json.get("_is_stub"):
        return True
    
    extraction = sum_json.get("extraction", {})
    if extraction.get("status") == "failed":
        return True
    
    # Check if all primary sections are empty
    sections = sum_json.get("sections", {})
    tldr = sections.get("tldr", [])
    what_moved = sections.get("what_moved_today", [])
    what_can_move = sections.get("what_can_move_tomorrow", [])
    
    if not tldr and not what_moved and not what_can_move:
        return True
    
    return False


def render_failed_summary(sum_json: Dict[str, Any], basename: str) -> html.Div:
    """Render failed/stub summary view."""
    extraction = sum_json.get("extraction", {})
    meta = sum_json.get("meta", {})
    
    reason = extraction.get("reason", "Unknown error")
    status = extraction.get("status", "unknown")
    title = meta.get("title", basename)
    provider = meta.get("provider", "Unknown")
    
    return html.Div([
        # Header
        html.Div([
            html.H2(title, style={
                'color': '#333',
                'marginBottom': '10px'
            }),
            html.Div([
                html.Span(f"Provider: {provider}", style={
                    'marginRight': '15px',
                    'color': '#666'
                }),
                html.Span(f"Status: {status}", style={
                    'color': '#666'
                })
            ], style={'marginBottom': '20px'}),
        ], style={
            'borderBottom': '2px solid #dc3545',
            'paddingBottom': '15px',
            'marginBottom': '20px'
        }),
        
        # Failed message
        html.Div([
            html.Div([
                html.I(className="fas fa-exclamation-triangle", style={
                    'fontSize': '48px',
                    'color': '#dc3545',
                    'marginBottom': '15px'
                }),
                html.H3("Failed Summary", style={
                    'color': '#dc3545',
                    'marginBottom': '15px'
                }),
                html.P(f"Reason: {reason}", style={
                    'fontSize': '16px',
                    'color': '#666',
                    'lineHeight': '1.6'
                }),
            ], style={
                'textAlign': 'center',
                'padding': '40px'
            })
        ], style={
            'backgroundColor': '#fff3cd',
            'border': '1px solid #ffc107',
            'borderRadius': '8px',
            'padding': '20px'
        }),
        
        # Back button
        html.Div([
            dcc.Link('← Back to Articles', href='/', style={
                'display': 'inline-block',
                'padding': '10px 20px',
                'backgroundColor': '#007bff',
                'color': 'white',
                'textDecoration': 'none',
                'borderRadius': '4px',
                'marginTop': '20px'
            })
        ])
    ], style={
        'maxWidth': '800px',
        'margin': '0 auto',
        'padding': '40px 20px'
    })


def render_summary_view(basename: str, sum_json: Dict[str, Any]) -> html.Div:
    """
    Render beautiful summary view from sum.json.
    
    Args:
        basename: Base filename
        sum_json: Parsed sum.json dict
    
    Returns:
        Dash html.Div with rendered summary
    """
    meta = sum_json.get("meta", {})
    sections = sum_json.get("sections", {})
    extraction = sum_json.get("extraction", {})
    
    # Extract metadata
    title = meta.get("title", basename)
    provider = meta.get("provider", "Unknown")
    products = meta.get("products", [])
    published_date = meta.get("published_date", "")
    horizon = meta.get("horizon", "u")
    
    # Fix provider if still a short code or "O" — extract from basename/title prefix
    if provider in ("O", "Unknown", "") or len(provider) <= 3:
        # Try to extract provider code from title prefix (e.g., "GM_Commodity...")
        raw_title = title or basename
        if "_" in raw_title:
            code = raw_title.split("_", 1)[0]
            _prefix_map = {
                "BOA": "Bank of America", "BA": "Barclays", "BR": "BlackRock",
                "DB": "Deutsche Bank", "GM": "Goldman Sachs", "HT": "HighTower Research",
                "JPM": "JP Morgan", "MZ": "Mizuho", "TSL": "TSLombard", "WF": "Wells Fargo",
                "SEB": "SEB Commodities", "R": "Rabobank", "MUFG": "MUFG", "ANZ": "ANZ",
                "BCA": "BCA", "BNPP": "BNPP", "BNY": "Bank of New York Melon",
                "CACIB": "CACIB", "CITI": "Citi", "HSBC": "HSBC", "ING": "ING",
                "MS": "Morgan Stanley", "NOM": "Nomura", "RBC": "RBC", "SG": "SocGen",
                "STI": "Stifel", "TME": "TME", "UBS": "UBS",
            }
            mapped = _prefix_map.get(code)
            if mapped:
                provider = mapped
    
    # Format date
    try:
        if len(published_date) == 8:  # YYYYMMDD
            from datetime import datetime
            dt = datetime.strptime(published_date, "%Y%m%d")
            date_display = dt.strftime("%B %d, %Y")
        else:
            date_display = published_date
    except:
        date_display = published_date
    
    # Horizon mapping
    horizon_map = {
        'y': 'Yearly',
        'q': 'Quarterly', 
        'm': 'Monthly',
        'w': 'Weekly',
        'd': 'Daily',
        'u': 'Unknown'
    }
    horizon_display = horizon_map.get(horizon, horizon)
    
    # Extraction status
    status = extraction.get("status", "ok")
    confidence = extraction.get("confidence_0_100", 100)
    
    # Build view
    children = []
    
    # Header section
    children.append(html.Div([
        html.H1(title, style={
            'color': '#004080',
            'marginBottom': '15px',
            'fontSize': '28px',
            'fontWeight': 'bold'
        }),
        
        # Metadata pills
        html.Div([
            html.Span(provider, style={
                'display': 'inline-block',
                'backgroundColor': '#004080',
                'color': 'white',
                'padding': '6px 12px',
                'borderRadius': '20px',
                'fontSize': '14px',
                'marginRight': '10px'
            }),
            html.Span(date_display, style={
                'display': 'inline-block',
                'backgroundColor': '#6c757d',
                'color': 'white',
                'padding': '6px 12px',
                'borderRadius': '20px',
                'fontSize': '14px',
                'marginRight': '10px'
            }),
            html.Span(horizon_display, style={
                'display': 'inline-block',
                'backgroundColor': '#28a745',
                'color': 'white',
                'padding': '6px 12px',
                'borderRadius': '20px',
                'fontSize': '14px',
                'marginRight': '10px' if products else '0px'
            }),
        ] + ([
            html.Span(
                ", ".join(products) if isinstance(products, list) else str(products),
                style={
                    'display': 'inline-block',
                    'backgroundColor': '#17a2b8',
                    'color': 'white',
                    'padding': '6px 12px',
                    'borderRadius': '20px',
                    'fontSize': '14px'
                }
            )
        ] if products else []), style={'marginBottom': '15px'}),
        
        # Status indicator
        html.Div([
            html.Span(f"Extraction: {status.upper()}", style={
                'color': '#28a745' if status == 'ok' else '#ffc107',
                'fontSize': '14px',
                'marginRight': '15px'
            }),
            html.Span(f"Confidence: {confidence}%", style={
                'color': '#28a745' if confidence >= 80 else ('#ffc107' if confidence >= 60 else '#dc3545'),
                'fontSize': '14px'
            }),
        ], style={'marginBottom': '10px'}),
        
        # Low confidence banner
        (html.Div([
            html.I(className="fas fa-exclamation-triangle", style={
                'marginRight': '10px'
            }),
            html.Span(f"Low Confidence ({confidence}%) - Review carefully"),
        ], style={
            'backgroundColor': '#fff3cd',
            'border': '1px solid #ffc107',
            'padding': '10px 15px',
            'borderRadius': '4px',
            'color': '#856404',
            'marginBottom': '15px'
        }) if confidence < 70 else html.Div()),
        
    ], style={
        'borderBottom': '2px solid #004080',
        'paddingBottom': '20px',
        'marginBottom': '30px'
    }))
    
    # TL;DR section (required)
    tldr = sections.get("tldr", [])
    if tldr:
        children.append(render_section(
            "TL;DR",
            tldr,
            icon="fas fa-bolt",
            bg_color="#e3f2fd",
            border_color="#004080"
        ))
    
    # What Moved Today
    what_moved = sections.get("what_moved_today", [])
    if what_moved:
        children.append(render_section(
            "What Moved Today",
            what_moved,
            icon="fas fa-chart-line"
        ))
    
    # What Can Move Tomorrow
    what_can_move = sections.get("what_can_move_tomorrow", [])
    if what_can_move:
        children.append(render_section(
            "What Can Move Tomorrow",
            what_can_move,
            icon="fas fa-calendar-alt"
        ))
    
    # Trade Ideas (cards)
    trade_ideas = sections.get("trade_ideas", [])
    if trade_ideas:
        children.append(render_trade_ideas(trade_ideas))
    
    # What Occurred
    what_occurred = sections.get("what_occurred", [])
    if what_occurred:
        children.append(render_section(
            "What Occurred",
            what_occurred,
            icon="fas fa-history"
        ))
    
    # Forward Watch
    forward_watch = sections.get("forward_watch", [])
    if forward_watch:
        children.append(render_section(
            "Forward Watch",
            forward_watch,
            icon="fas fa-binoculars"
        ))
    
    # Warnings
    warnings = sections.get("warnings", [])
    if warnings:
        children.append(render_section(
            "Warnings",
            warnings,
            icon="fas fa-exclamation-triangle",
            bg_color="#fff3cd",
            border_color="#ffc107"
        ))
    
    # Tips & Reminders
    tips = sections.get("tips_reminders", [])
    if tips:
        children.append(render_section(
            "Tips & Reminders",
            tips,
            icon="fas fa-lightbulb"
        ))
    
    # Cross-Asset Impacts
    cross_asset = sections.get("cross_asset_impacts", [])
    if cross_asset:
        children.append(render_section(
            "Cross-Asset Impacts",
            cross_asset,
            icon="fas fa-exchange-alt"
        ))
    
    # Scenarios
    scenarios = sections.get("scenarios", [])
    if scenarios:
        children.append(render_section(
            "Scenarios",
            scenarios,
            icon="fas fa-map-signs"
        ))
    
    # Fingerprint Quotes (collapsible)
    fingerprint_quotes = sum_json.get("fingerprint_quotes", [])
    if fingerprint_quotes:
        children.append(render_collapsible_section(
            "Fingerprint Quotes",
            [html.Blockquote(quote, style={
                'borderLeft': '4px solid #004080',
                'paddingLeft': '15px',
                'marginBottom': '15px',
                'fontStyle': 'italic',
                'color': '#666'
            }) for quote in fingerprint_quotes]
        ))
    
    # Numeric Claims (collapsible table)
    numeric_claims = sum_json.get("numeric_claims", [])
    if numeric_claims:
        children.append(render_numeric_claims(numeric_claims))
    
    # Back button
    children.append(html.Div([
        dcc.Link('← Back to Articles', href='/', style={
            'display': 'inline-block',
            'padding': '10px 20px',
            'backgroundColor': '#007bff',
            'color': 'white',
            'textDecoration': 'none',
            'borderRadius': '4px',
            'marginTop': '30px'
        })
    ]))
    
    return html.Div(children, style={
        'maxWidth': '900px',
        'margin': '0 auto',
        'padding': '40px 20px',
        'backgroundColor': 'white'
    })


def render_section(title: str, bullets: list, icon: str = "fas fa-circle", 
                   bg_color: str = "#f8f9fa", border_color: str = "#dee2e6") -> html.Div:
    """Render a section with bullets."""
    return html.Div([
        html.H3([
            html.I(className=icon, style={'marginRight': '10px'}),
            title
        ], style={
            'color': '#004080',
            'fontSize': '22px',
            'marginBottom': '15px'
        }),
        html.Ul([
            html.Li(bullet if isinstance(bullet, str) else bullet.get('text', str(bullet)), style={
                'marginBottom': '10px',
                'lineHeight': '1.6'
            }) for bullet in bullets
        ], style={
            'paddingLeft': '25px'
        })
    ], style={
        'backgroundColor': bg_color,
        'border': f'1px solid {border_color}',
        'borderRadius': '8px',
        'padding': '20px',
        'marginBottom': '25px'
    })


def render_trade_ideas(trade_ideas: list) -> html.Div:
    """Render trade ideas as cards."""
    cards = []
    
    for idea in trade_ideas:
        if isinstance(idea, dict):
            product = idea.get('product', 'Unknown')
            bias = idea.get('bias', 'Neutral')
            catalyst = idea.get('catalyst', '')
            setup = idea.get('setup', '')
            key_levels = idea.get('key_levels', [])
            risk = idea.get('risk', '')
            time_horizon = idea.get('time_horizon', '')
            
            # Bias color
            bias_color = {
                'Bullish': '#28a745',
                'Bearish': '#dc3545',
                'Neutral': '#6c757d'
            }.get(bias, '#6c757d')
            
            cards.append(html.Div([
                # Header
                html.Div([
                    html.H4(product, style={
                        'color': '#004080',
                        'margin': '0',
                        'fontSize': '20px'
                    }),
                    html.Span(bias, style={
                        'backgroundColor': bias_color,
                        'color': 'white',
                        'padding': '4px 12px',
                        'borderRadius': '12px',
                        'fontSize': '14px'
                    })
                ], style={
                    'display': 'flex',
                    'justifyContent': 'space-between',
                    'alignItems': 'center',
                    'marginBottom': '15px'
                }),
                
                # Content
                (html.Div([
                    html.Strong("Catalyst: "),
                    html.Span(catalyst)
                ], style={'marginBottom': '10px'}) if catalyst else html.Div()),
                
                (html.Div([
                    html.Strong("Setup: "),
                    html.Span(setup)
                ], style={'marginBottom': '10px'}) if setup else html.Div()),
                
                (html.Div([
                    html.Strong("Key Levels: "),
                    html.Span(', '.join(str(level) for level in key_levels))
                ], style={'marginBottom': '10px'}) if key_levels else html.Div()),
                
                (html.Div([
                    html.Strong("Risk: "),
                    html.Span(risk)
                ], style={'marginBottom': '10px'}) if risk else html.Div()),
                
                (html.Div([
                    html.Strong("Time Horizon: "),
                    html.Span(time_horizon)
                ]) if time_horizon else html.Div()),
                
            ], style={
                'backgroundColor': 'white',
                'border': '1px solid #dee2e6',
                'borderRadius': '8px',
                'padding': '20px',
                'marginBottom': '15px',
                'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'
            }))
    
    if not cards:
        return html.Div()
    
    return html.Div([
        html.H3([
            html.I(className="fas fa-lightbulb", style={'marginRight': '10px'}),
            "Trade Ideas"
        ], style={
            'color': '#004080',
            'fontSize': '22px',
            'marginBottom': '15px'
        }),
        html.Div(cards)
    ], style={'marginBottom': '25px'})


def render_collapsible_section(title: str, content: list) -> html.Div:
    """Render a collapsible section."""
    section_id = title.lower().replace(' ', '-')
    
    return html.Details([
        html.Summary(title, style={
            'color': '#004080',
            'fontSize': '20px',
            'fontWeight': 'bold',
            'cursor': 'pointer',
            'padding': '15px',
            'backgroundColor': '#f8f9fa',
            'border': '1px solid #dee2e6',
            'borderRadius': '8px',
            'marginBottom': '10px'
        }),
        html.Div(content, style={
            'padding': '20px',
            'backgroundColor': 'white',
            'border': '1px solid #dee2e6',
            'borderTop': 'none',
            'borderRadius': '0 0 8px 8px',
            'marginBottom': '25px'
        })
    ])


def render_numeric_claims(numeric_claims: list) -> html.Div:
    """Render numeric claims as collapsible table."""
    if not numeric_claims:
        return html.Div()
    
    rows = []
    for claim in numeric_claims:
        if isinstance(claim, dict):
            value = claim.get('value', '')
            context = claim.get('context', '')
            source_quote = claim.get('source_quote', '')
            
            rows.append(html.Tr([
                html.Td(value, style={
                    'padding': '10px',
                    'borderBottom': '1px solid #dee2e6'
                }),
                html.Td(context, style={
                    'padding': '10px',
                    'borderBottom': '1px solid #dee2e6'
                }),
                html.Td(source_quote, style={
                    'padding': '10px',
                    'borderBottom': '1px solid #dee2e6',
                    'fontSize': '14px',
                    'fontStyle': 'italic',
                    'color': '#666'
                })
            ]))
    
    table = html.Table([
        html.Thead(html.Tr([
            html.Th("Value", style={
                'padding': '10px',
                'backgroundColor': '#004080',
                'color': 'white',
                'borderBottom': '2px solid #003060'
            }),
            html.Th("Context", style={
                'padding': '10px',
                'backgroundColor': '#004080',
                'color': 'white',
                'borderBottom': '2px solid #003060'
            }),
            html.Th("Source Quote", style={
                'padding': '10px',
                'backgroundColor': '#004080',
                'color': 'white',
                'borderBottom': '2px solid #003060'
            })
        ])),
        html.Tbody(rows)
    ], style={
        'width': '100%',
        'borderCollapse': 'collapse',
        'backgroundColor': 'white'
    })
    
    return render_collapsible_section("Numeric Claims", [table])
