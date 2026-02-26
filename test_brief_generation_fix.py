"""
Test: Brief Generation Fix Validation

This test validates that:
1. Given events saved for a date
2. When generation runs
3. The brief field is persisted and returned by the recap endpoint for that same date

Run with: python test_brief_generation_fix.py
"""

import unittest
import tempfile
import os
from pathlib import Path


class TestBriefGenerationFix(unittest.TestCase):
    """Tests for the brief generation and persistence fix."""

    @classmethod
    def setUpClass(cls):
        """Create a temporary test database."""
        cls.temp_dir = tempfile.mkdtemp()
        cls.test_db = Path(cls.temp_dir) / "test_econ.db"
        
        # Initialize database schema
        from econ_calendar_db import get_connection
        conn = get_connection(cls.test_db)
        conn.close()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up temporary files."""
        import shutil
        if os.path.exists(cls.temp_dir):
            shutil.rmtree(cls.temp_dir)

    def test_brief_generated_and_persisted(self):
        """
        Test that brief generation creates a persisted brief row.
        
        Steps:
        1. Insert test events for a date
        2. Run generate_for_date
        3. Verify brief exists and has valid content
        """
        from econ_calendar_store import (
            upsert_week_and_events,
            get_events_for_date,
            get_daily_brief,
        )
        from econ_calendar_parser import ParsedEvent
        
        # 1. Insert test events
        test_date = "2099-01-15"  # Future date unlikely to have real data
        events = [
            ParsedEvent(
                event_date=test_date,
                time_local="10:00",
                all_day=False,
                country_or_region="United States",
                currency_tag="USD",
                title="Test CPI Release",
            ),
            ParsedEvent(
                event_date=test_date,
                time_local="14:30",
                all_day=False,
                country_or_region="United States",
                currency_tag="USD",
                title="Fed Chair Speaks",
            ),
        ]
        
        upsert_week_and_events(
            self.test_db,
            "2099-01-12",  # week start
            "2099-01-18",  # week end
            "Test week raw text",
            events,
        )
        
        # Verify events exist
        stored_events = get_events_for_date(self.test_db, test_date)
        self.assertEqual(len(stored_events), 2, "Events should be persisted")
        
        # 2. Run generate_for_date
        from econ_calendar_ai import generate_for_date
        
        result = generate_for_date(
            test_date,
            dynamics_mode=True,
            db_path=self.test_db,
            rollups_daily_dir=None,  # No rollup context
        )
        
        # Check result dict
        self.assertIsInstance(result, dict, "Result should be a dict")
        self.assertEqual(result.get("date_iso"), test_date, "Result should have correct date")
        self.assertIsNone(result.get("error"), f"No error expected, got: {result.get('error')}")
        
        # 3. Verify brief persisted
        brief = get_daily_brief(self.test_db, test_date)
        self.assertIsNotNone(brief, "Brief row should exist")
        self.assertIsInstance(brief, dict, "Brief should be a dict")
        
        theory_text = brief.get("theory_text", "")
        self.assertTrue(len(theory_text) > 50, f"theory_text should have content, got {len(theory_text)} chars")
        
        # Verify it's not an error message
        error_prefixes = (
            "brief generation unavailable",
            "summary unavailable",
            "summary generation failed",
            "error code:",
        )
        self.assertFalse(
            any(theory_text.lower().startswith(p) for p in error_prefixes),
            "theory_text should not be an error message"
        )
        
        print(f"\nOK: Brief generated and persisted for {test_date}")
        print(f"  theory_text: {theory_text[:100]}...")

    def test_error_not_persisted_as_content(self):
        """
        Test that LLM errors are NOT saved as theory_text content.
        
        This validates the fix for the bug where error messages were
        stored as theory_text content.
        """
        from econ_calendar_ai import generate_daily_brief_ai
        from unittest.mock import patch, MagicMock
        
        # Mock the LLM client to raise an error
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("Test LLM error")
        
        with patch("econ_calendar_ai._get_llm_client", return_value=mock_client):
            result = generate_daily_brief_ai(
                "2099-01-01",
                events=[{"time_local": "10:00", "title": "Test", "currency_tag": "USD", "country_or_region": "US"}],
                ranked=[],
                macro_context_text="",
                dynamics_mode=True,
                db_path=None,
            )
        
        # Verify error handling
        self.assertIsInstance(result, dict)
        self.assertTrue(result.get("is_error"), "is_error flag should be True")
        self.assertEqual(result.get("theory_text"), "", "theory_text should be empty on error")
        
        print("\nOK: LLM errors are not persisted as content")

    def test_same_date_key_for_write_and_read(self):
        """
        Test that the same date key format (YYYY-MM-DD) is used consistently.
        """
        from econ_calendar_store import upsert_daily_brief, get_daily_brief
        
        test_date = "2099-06-15"
        test_theory = "Test theory content for date key validation."
        test_dynamics = "Test dynamics content."
        
        # Write with YYYY-MM-DD format
        upsert_daily_brief(
            self.test_db,
            test_date,
            "test_context_hash",
            "test_events_hash",
            test_theory,
            test_dynamics,
        )
        
        # Read back with same format
        brief = get_daily_brief(self.test_db, test_date)
        
        self.assertIsNotNone(brief, "Brief should be found with same date key")
        self.assertEqual(brief.get("theory_text"), test_theory)
        self.assertEqual(brief.get("dynamics_text"), test_dynamics)
        
        print("\nOK: Date key format (YYYY-MM-DD) is consistent for write and read")


if __name__ == "__main__":
    unittest.main(verbosity=2)

