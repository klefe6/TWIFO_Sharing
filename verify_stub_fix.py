"""
Quick verification of the stub threshold fix.
Demonstrates the new behavior without hitting actual LLMs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def demo_stub_logic():
    """
    Simulate the new stub threshold logic.
    Shows what happens with different text lengths.
    """
    
    STUB_THRESHOLD_CHARS = 100
    MIN_TEXT_CHARS = 1500
    
    test_cases = [
        (0, "ok", "Empty document"),
        (50, "ok", "Tiny extraction (50 chars)"),
        (99, "ok", "Just below threshold (99 chars)"),
        (100, "ok", "Exactly at threshold (100 chars)"),
        (500, "ok", "Low quality (500 chars)"),
        (1000, "ok", "Low quality (1000 chars)"),
        (1000, "failed", "Failed but has text (1000 chars)"),
        (1000, "degraded", "Degraded with text (1000 chars)"),
        (1500, "ok", "Normal quality (1500 chars)"),
        (5000, "ok", "Good quality (5000 chars)"),
        (5000, "degraded", "Good text, degraded extraction (5000 chars)"),
    ]
    
    print("=" * 80)
    print("STUB THRESHOLD FIX — Behavior Verification")
    print("=" * 80)
    print()
    
    for chars, status, desc in test_cases:
        # Step 1: Check for truly unusable text (stub condition)
        if chars < STUB_THRESHOLD_CHARS:
            result = "[STUB] No summarization"
            low_conf = None
        # Step 2: Check for low quality but usable
        elif status == "failed" or chars < MIN_TEXT_CHARS:
            result = "[SUMMARY] With low_confidence=True"
            if status == "failed":
                low_conf = "failed_extraction_but_has_text"
            else:
                low_conf = f"insufficient_text_chars_{chars}"
        else:
            result = "[SUMMARY] Normal"
            low_conf = None
        
        print(f"{desc:50} -> {result}")
        if low_conf:
            print(f"{'':50}   +- reason: {low_conf}")
        print()
    
    print("=" * 80)
    print("Summary:")
    print("  - Text < 100 chars: Always stub")
    print("  - Text 100-1499 chars: Summary with low_confidence warning")
    print("  - Text >= 1500 chars: Normal summary")
    print("  - extraction_status='failed' + text: Summary with low_confidence")
    print("=" * 80)


if __name__ == "__main__":
    demo_stub_logic()
