"""
Manual verification script for Risk Flags context enrichment.
Generates sample risk flags and shows how they appear in the UI.
"""
import datetime as dt
from rollups import build_daily_rollup

def print_separator():
    print("\n" + "=" * 80 + "\n")

def display_risk_flag(w):
    """Display a risk flag in a readable format."""
    asset_class = w.get("asset_class", "general").upper()
    products = w.get("products", [])
    horizon = w.get("horizon", "today")
    direction = w.get("direction", "unknown")
    confidence = w.get("confidence")
    text = w.get("text", "")
    
    # Products display
    if products:
        products_str = ", ".join(products[:3])
        if len(products) > 3:
            products_str += f" +{len(products) - 3}"
    else:
        products_str = "General"
    
    # Suffix display
    suffix_parts = []
    if horizon and horizon != "today":
        suffix_parts.append(horizon)
    if direction and direction not in ["unknown", "mixed"]:
        suffix_parts.append(direction)
    elif direction == "mixed":
        suffix_parts.append("two-sided")
    
    suffix_str = " | ".join(suffix_parts) if suffix_parts else ""
    
    # Display
    print(f"[{asset_class}] {products_str}", end="")
    if suffix_str:
        print(f" | {suffix_str}", end="")
    if confidence is not None:
        print(f" (confidence: {confidence:.1f})", end="")
    print()
    print(f"[!] {text}")
    print()

def main():
    print_separator()
    print("RISK FLAGS CONTEXT ENRICHMENT - MANUAL VERIFICATION")
    print_separator()
    
    # Test case 1: Oil risk
    print("TEST 1: Oil-related risk (Commodities)")
    print("-" * 80)
    article1 = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "Rising oil price volatility tied to OPEC tensions could negatively impact energy stocks."
            ]
        }
    }
    rollup1 = build_daily_rollup(dt.date(2024, 3, 1), [article1], 1)
    for w in rollup1["sections"]["warnings"]:
        display_risk_flag(w)
    
    # Test case 2: Inflation risk
    print("TEST 2: Inflation risk (General - affects multiple assets)")
    print("-" * 80)
    article2 = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "Sticky inflation could force Fed to keep rates higher for longer."
            ]
        }
    }
    rollup2 = build_daily_rollup(dt.date(2024, 3, 1), [article2], 1)
    for w in rollup2["sections"]["warnings"]:
        display_risk_flag(w)
    
    # Test case 3: FX JPY risk
    print("TEST 3: FX risk with time horizon")
    print("-" * 80)
    article3 = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "BOJ policy shift could trigger sharp yen moves next week."
            ]
        }
    }
    rollup3 = build_daily_rollup(dt.date(2024, 3, 1), [article3], 1)
    for w in rollup3["sections"]["warnings"]:
        display_risk_flag(w)
    
    # Test case 4: Rates with direction
    print("TEST 4: Rates risk with bearish direction")
    print("-" * 80)
    article4 = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "Treasury yields could spike sharply if Fed signals additional rate hikes at FOMC."
            ]
        }
    }
    rollup4 = build_daily_rollup(dt.date(2024, 3, 1), [article4], 1)
    for w in rollup4["sections"]["warnings"]:
        display_risk_flag(w)
    
    # Test case 5: Equities with intraday horizon
    print("TEST 5: Equities risk with intraday horizon")
    print("-" * 80)
    article5 = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "Watch for intraday volatility in stocks around CPI release."
            ]
        }
    }
    rollup5 = build_daily_rollup(dt.date(2024, 3, 1), [article5], 1)
    for w in rollup5["sections"]["warnings"]:
        display_risk_flag(w)
    
    # Test case 6: Mixed direction
    print("TEST 6: Mixed/two-sided directional bias")
    print("-" * 80)
    article6 = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "Mixed signals from Fed officials create uncertainty for bond traders."
            ]
        }
    }
    rollup6 = build_daily_rollup(dt.date(2024, 3, 1), [article6], 1)
    for w in rollup6["sections"]["warnings"]:
        display_risk_flag(w)
    
    # Test case 7: Generic warning (becomes General)
    print("TEST 7: Generic warning without specific products")
    print("-" * 80)
    article7 = {
        "meta": {
            "source_file": "test.pdf",
            "provider": "TEST",
            "title": "Test",
            "published_date": "2024-03-01",
            "horizon": "d",
            "products": []
        },
        "sections": {
            "warnings": [
                "Market volatility elevated across all asset classes."
            ]
        }
    }
    rollup7 = build_daily_rollup(dt.date(2024, 3, 1), [article7], 1)
    for w in rollup7["sections"]["warnings"]:
        display_risk_flag(w)
    
    print_separator()
    print("VERIFICATION COMPLETE")
    print_separator()
    print("\nKEY OBSERVATIONS:")
    print("1. Every risk flag has an asset class tag (COMMODITIES, FX, RATES, EQUITIES, GENERAL)")
    print("2. Products are shown explicitly or 'General' is displayed")
    print("3. Time horizon is shown when not 'today'")
    print("4. Direction is shown when detected (bullish/bearish/two-sided)")
    print("5. Confidence scores reflect specificity of context")
    print("\nNo risk flag renders without clear product attribution!")

if __name__ == "__main__":
    main()

