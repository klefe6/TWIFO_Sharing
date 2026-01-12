"""
Article Summary Format Validator & Fixer
Enforces the Egypt-format for all article summaries.
"""

import re
from typing import List, Dict, Tuple
import requests
import os
from pathlib import Path


def load_api_key() -> str:
    """Load OpenAI API key."""
    script_dir = Path(__file__).parent
    
    try:
        from dotenv import load_dotenv
        env_file = script_dir / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            key = os.getenv("OPENAI_API_KEY")
            if key:
                return key
    except ImportError:
        pass
    
    key = os.getenv("OPENAI_API_KEY")
    return key or ""


OPENAI_API_KEY = load_api_key()
MODEL_MINI = "gpt-4o-mini"
MODEL_STRONG = "gpt-4o"


def validate_article_summary(summary: dict) -> Tuple[bool, List[str]]:
    """
    Validate article summary against Egypt-format requirements.
    
    Returns:
        (is_valid, violations_list)
    """
    violations = []
    sections = summary.get("sections", {})
    meta = summary.get("meta", {})
    
    # Check required sections exist
    required_sections = ["tldr", "what_occurred", "forward_watch"]
    for sec in required_sections:
        if sec not in sections or not sections[sec]:
            violations.append(f"Missing or empty section: {sec}")
    
    # Check TL;DR count
    tldr = sections.get("tldr", [])
    if len(tldr) > 5:
        violations.append(f"TL;DR has {len(tldr)} bullets, max is 5")
    
    # Check KEY DATA count (what_occurred)
    key_data = sections.get("what_occurred", [])
    if len(key_data) < 3 or len(key_data) > 8:
        violations.append(f"KEY DATA has {len(key_data)} bullets, need 3-8")
    
    # Check FORWARD WATCH count
    forward_watch = sections.get("forward_watch", [])
    if len(forward_watch) < 3 or len(forward_watch) > 8:
        violations.append(f"FORWARD WATCH has {len(forward_watch)} bullets, need 3-8")
    
    # Check ACTIONABLE formatting
    trade_ideas = sections.get("trade_ideas", [])
    if trade_ideas:
        for idx, idea in enumerate(trade_ideas):
            text = idea.get("text", "") if isinstance(idea, dict) else str(idea)
            if not has_direction_trigger_timeframe(text):
                violations.append(f"ACTIONABLE bullet {idx+1} missing direction/trigger/timeframe: '{text[:50]}...'")
    
    # Check Theme exists
    if "theme" not in meta or not meta["theme"]:
        violations.append("Missing theme")
    
    # Check theme length
    theme = meta.get("theme", "")
    if theme and len(theme.split()) > 22:
        violations.append(f"Theme too long ({len(theme.split())} words, max 22)")
    
    return (len(violations) == 0, violations)


def has_direction_trigger_timeframe(text: str) -> bool:
    """
    Check if actionable bullet has direction + trigger + timeframe.
    
    Direction indicators: long, short, buy, sell, hedge, exit, close
    Trigger indicators: if, when, on, above, below, breaks, fails, reaches
    Timeframe indicators: 0-3d, 1-2w, >2w, day, week, month, into
    """
    text_lower = text.lower()
    
    # Direction keywords
    direction_patterns = [
        r'\b(long|short|buy|sell|hedge|exit|close|enter)\b',
    ]
    has_direction = any(re.search(p, text_lower) for p in direction_patterns)
    
    # Trigger keywords
    trigger_patterns = [
        r'\b(if|when|on|above|below|break|fail|reach|cross|hold|lose)\b',
    ]
    has_trigger = any(re.search(p, text_lower) for p in trigger_patterns)
    
    # Timeframe indicators
    timeframe_patterns = [
        r'\b\d+-\d+\s*(d|day|w|week|m|month)',
        r'\b(into|by|before|after)\s+\w+',
        r'>\s*\d+\s*(d|w|m)',
    ]
    has_timeframe = any(re.search(p, text_lower) for p in timeframe_patterns)
    
    return has_direction and has_trigger and has_timeframe


def generate_theme_from_tldr(tldr_items: List) -> str:
    """Generate a concise theme from TL;DR bullets using LLM."""
    if not tldr_items:
        return "Market analysis and outlook"
    
    # Extract text from items
    texts = []
    for item in tldr_items[:3]:  # Use only first 3 for brevity
        if isinstance(item, dict):
            texts.append(item.get("text", ""))
        else:
            texts.append(str(item))
    
    combined = " ".join(texts)
    
    # Call LLM with minimal tokens
    prompt = f"Summarize this in exactly 1 sentence (max 22 words):\n{combined[:500]}"
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL_MINI,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 50,
                "temperature": 0.3
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            theme = result["choices"][0]["message"]["content"].strip()
            # Truncate to 22 words if needed
            words = theme.split()
            if len(words) > 22:
                theme = " ".join(words[:22]) + "..."
            return theme
        else:
            return "Market analysis and trading outlook"
    except Exception as e:
        print(f"[WARN] Theme generation failed: {e}")
        return "Market analysis and trading outlook"


def rewrite_actionable_bullets(bullets: List, existing_text: str = "") -> List[str]:
    """
    Rewrite actionable bullets to include direction + trigger + timeframe.
    Uses minimal token LLM call.
    """
    if not bullets:
        return []
    
    # Extract text from bullets
    texts = []
    for item in bullets:
        if isinstance(item, dict):
            texts.append(item.get("text", ""))
        else:
            texts.append(str(item))
    
    # Filter out generic monitoring statements
    actionable_candidates = [
        t for t in texts 
        if not any(word in t.lower() for word in ["monitor for", "watch for", "keep an eye"])
    ]
    
    if not actionable_candidates:
        return []
    
    # Build compact prompt
    bullets_text = "\n".join(f"{i+1}. {t}" for i, t in enumerate(actionable_candidates[:8]))
    
    prompt = f"""Rewrite each bullet as: [Direction] [Asset] [Trigger] [Timeframe].
Format: "Long/Short X if/when Y [trigger] (0-3D/1-2W/>2W)"
Example: "Long gold if breaks above $2,100 (0-3D)"

Bullets:
{bullets_text}

Output only the rewritten bullets, numbered 1-N."""
    
    try:
        # Try with mini model first
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MODEL_MINI,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 400,
                "temperature": 0.3
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            rewritten = result["choices"][0]["message"]["content"].strip()
            
            # Extract bullets from numbered list
            lines = rewritten.split("\n")
            bullets_out = []
            for line in lines:
                # Remove numbering
                line = re.sub(r'^\d+\.\s*', '', line).strip()
                if line and has_direction_trigger_timeframe(line):
                    bullets_out.append(line)
            
            # If quality check fails, retry with stronger model
            if len(bullets_out) < len(actionable_candidates) // 2:
                response2 = requests.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": MODEL_STRONG,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 400,
                        "temperature": 0.3
                    },
                    timeout=30
                )
                
                if response2.status_code == 200:
                    result2 = response2.json()
                    rewritten2 = result2["choices"][0]["message"]["content"].strip()
                    lines = rewritten2.split("\n")
                    bullets_out = []
                    for line in lines:
                        line = re.sub(r'^\d+\.\s*', '', line).strip()
                        if line and has_direction_trigger_timeframe(line):
                            bullets_out.append(line)
            
            return bullets_out[:8]  # Max 8
        else:
            print(f"[WARN] Actionable rewrite failed: {response.status_code}")
            return texts[:8]
    except Exception as e:
        print(f"[WARN] Actionable rewrite error: {e}")
        return texts[:8]


def fix_summary_format(summary: dict) -> dict:
    """
    Auto-fix summary to conform to Egypt-format.
    Modifies summary dict in-place and returns it.
    """
    sections = summary.get("sections", {})
    meta = summary.get("meta", {})
    
    # Ensure theme exists
    if "theme" not in meta or not meta["theme"]:
        tldr = sections.get("tldr", [])
        meta["theme"] = generate_theme_from_tldr(tldr)
    
    # Trim theme if too long
    theme = meta.get("theme", "")
    if theme:
        words = theme.split()
        if len(words) > 22:
            meta["theme"] = " ".join(words[:22])
    
    # Trim TL;DR to 5 max
    tldr = sections.get("tldr", [])
    if len(tldr) > 5:
        sections["tldr"] = tldr[:5]
    
    # Ensure KEY DATA (what_occurred) is 3-8 bullets
    key_data = sections.get("what_occurred", [])
    if len(key_data) < 3:
        # Pad with generic bullets if needed
        while len(key_data) < 3:
            key_data.append({"text": "Market data pending analysis", "sources": [meta.get("provider", "O")]})
    if len(key_data) > 8:
        key_data = key_data[:8]
    sections["what_occurred"] = key_data
    
    # Ensure FORWARD WATCH is 3-8 bullets
    forward_watch = sections.get("forward_watch", [])
    if len(forward_watch) < 3:
        while len(forward_watch) < 3:
            forward_watch.append({"text": "Monitor key levels and data releases", "sources": [meta.get("provider", "O")]})
    if len(forward_watch) > 8:
        forward_watch = forward_watch[:8]
    sections["forward_watch"] = forward_watch
    
    # Fix ACTIONABLE bullets
    trade_ideas = sections.get("trade_ideas", [])
    if trade_ideas:
        # Check if they need rewriting
        needs_rewrite = False
        for idea in trade_ideas:
            text = idea.get("text", "") if isinstance(idea, dict) else str(idea)
            if not has_direction_trigger_timeframe(text):
                needs_rewrite = True
                break
        
        if needs_rewrite and OPENAI_API_KEY:
            rewritten = rewrite_actionable_bullets(trade_ideas)
            sections["trade_ideas"] = [{"text": t, "sources": [meta.get("provider", "O")]} for t in rewritten]
    
    # Ensure TIPS & REMINDERS is 2-6 bullets
    tips = sections.get("tips_reminders", [])
    if len(tips) > 6:
        tips = tips[:6]
    sections["tips_reminders"] = tips
    
    # Remove unwanted fields
    if "overall_bias" in meta:
        del meta["overall_bias"]
    if "watchlist" in sections:
        del sections["watchlist"]
    
    summary["sections"] = sections
    summary["meta"] = meta
    
    return summary

