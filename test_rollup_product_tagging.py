"""
Test: Rollup Product Tagging
Purpose: Verify bullets are product-specific, not ALL_PRODUCTS; General bucket for unassigned
Author: Kevin Lefebvre
Last Updated: 2026-02-05
"""

from datetime import date
from rollups import build_daily_rollup, GENERAL_BUCKET, PRODUCT_CODES


def test_btc_section_not_equal_gc_section():
    """Fixture with mixed topics: BTC section != GC section (not identical)."""
    article_btc = {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {"provider": "X", "title": "BTC Article", "products": ["BTC"]},
        "sections": {
            "what_occurred": [
                {"text": "Bitcoin rallied past 45,000 on institutional inflows", "sources": ["X"], "products": ["BTC"]},
            ],
            "forward_watch": [
                {"text": "Watch BTC support at 43,000", "sources": ["X"], "products": ["BTC"]},
            ],
            "trade_ideas": [],
            "tldr": [],
        },
    }
    article_gc = {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {"provider": "Y", "title": "GC Article", "products": ["GC"]},
        "sections": {
            "what_occurred": [
                {"text": "Gold fell as Treasury yields rose", "sources": ["Y"], "products": ["GC"]},
            ],
            "forward_watch": [
                {"text": "GC resistance at 2,050", "sources": ["Y"], "products": ["GC"]},
            ],
            "trade_ideas": [],
            "tldr": [],
        },
    }
    rollup = build_daily_rollup(date(2026, 2, 5), [article_btc, article_gc], min_articles_required=1)

    obs = rollup.get("sections", {}).get("observations", {})
    fw = rollup.get("sections", {}).get("forward_watch", {})

    btc_obs = [it.get("text", "") for it in obs.get("BTC", [])]
    gc_obs = [it.get("text", "") for it in obs.get("GC", [])]
    assert btc_obs != gc_obs, "BTC and GC sections must not be identical"
    assert "Bitcoin rallied" in str(btc_obs) or "BTC" in str(obs.get("BTC", []))
    assert "Gold fell" in str(gc_obs) or "GC" in str(obs.get("GC", []))
    print("[PASS] BTC section != GC section (not identical)")


def test_no_bullet_has_all_products():
    """Assert: no bullet has products == ALL_PRODUCTS unless explicitly intended."""
    all_products = set(PRODUCT_CODES)
    article = {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {"provider": "X", "products": list(all_products)},
        "sections": {
            "what_occurred": [
                {"text": "Gold rallied", "sources": ["X"]},  # No products - should infer GC or go to General
                {"text": "Bitcoin volatility spiked", "sources": ["X"], "products": ["BTC"]},
            ],
            "forward_watch": [],
            "trade_ideas": [],
            "tldr": [],
        },
    }
    rollup = build_daily_rollup(date(2026, 2, 5), [article], min_articles_required=1)
    obs = rollup.get("sections", {}).get("observations", {})

    for product, items in obs.items():
        for it in items:
            prods = it.get("products", [])
            assert set(prods) != all_products, f"Bullet must not have ALL_PRODUCTS: {it}"
            assert len(prods) <= len(all_products), f"Bullet products cannot exceed known products: {prods}"
    print("[PASS] No bullet has products == ALL_PRODUCTS")


def test_products_empty_goes_to_general():
    """Assert: products=[] bullets go to General, not all product sections."""
    article = {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {"provider": "X", "products": ["BTC", "GC", "ES"]},
        "sections": {
            "what_occurred": [
                {"text": "Broad macro uncertainty persists", "sources": ["X"], "products": []},
                {"text": "Fed meeting next week", "sources": ["X"]},  # No products key
            ],
            "forward_watch": [],
            "trade_ideas": [],
            "tldr": [],
        },
    }
    rollup = build_daily_rollup(date(2026, 2, 5), [article], min_articles_required=1)
    obs = rollup.get("sections", {}).get("observations", {})

    general_items = obs.get(GENERAL_BUCKET, [])
    general_texts = [it.get("text", "") for it in general_items]
    assert "Broad macro" in str(general_texts) or "Fed meeting" in str(general_texts), \
        f"Unassigned bullets should be in General: {obs}"

    for product in ["BTC", "GC", "ES"]:
        product_items = obs.get(product, [])
        for it in product_items:
            assert it.get("text") not in ["Broad macro uncertainty persists", "Fed meeting next week"], \
                f"Unassigned bullet must not appear under {product}"
    print("[PASS] products=[] bullets go to General, not all product sections")


def test_dedupe_identical_bullet():
    """Dedupe: identical bullet text appears once per section."""
    article = {
        "schema_version": "twifo.sum.v1",
        "kind": "article",
        "meta": {"provider": "X", "products": ["GC"]},
        "sections": {
            "what_occurred": [
                {"text": "Gold rallied on safe-haven demand", "sources": ["X"], "products": ["GC"]},
                {"text": "Gold rallied on safe-haven demand", "sources": ["Y"], "products": ["GC"]},
            ],
            "forward_watch": [],
            "trade_ideas": [],
            "tldr": [],
        },
    }
    rollup = build_daily_rollup(date(2026, 2, 5), [article], min_articles_required=1)
    obs = rollup.get("sections", {}).get("observations", {})
    gc_items = obs.get("GC", [])
    gc_texts = [it.get("text", "") for it in gc_items]
    assert gc_texts.count("Gold rallied on safe-haven demand") <= 1, \
        f"Identical bullet should appear once (deduped): {gc_texts}"
    print("[PASS] Identical bullet deduped")


if __name__ == "__main__":
    test_btc_section_not_equal_gc_section()
    test_no_bullet_has_all_products()
    test_products_empty_goes_to_general()
    test_dedupe_identical_bullet()
    print("\nAll product tagging tests passed.")
