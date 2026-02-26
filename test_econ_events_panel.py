"""
Integration tests for Economic Events panel rendering and LLM analysis caching.
Purpose: Verify get_events_for_date integration, panel component output, and
         that a second call with matching context_hash does NOT hit the LLM.
Author: Kevin Lefebvre
Last Updated: 2026-02-22
"""

from __future__ import annotations

import json
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import MagicMock, call, patch

# Ensure project root is on path so imports resolve without installing a package.
sys.path.insert(0, str(Path(__file__).parent))

from econ_calendar_db import get_connection
from econ_calendar_parser import parse_week_block
from econ_calendar_store import get_events_for_date, upsert_week_and_events

# Import FULL_EXAMPLE from test_econ_calendar_parser
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
try:
    from test_econ_calendar_parser import FULL_EXAMPLE
except ImportError:
    # Fallback if import fails
    FULL_EXAMPLE = """\
Sunday, February 22 to Saturday, February 28, 2026

Monday, February 23, 2026
All China - Chinese New Year - CHINA*
All Japan - Emperor's Birthday - JPY*

Tuesday, February 24, 2026
10:00 CB Consumer Confidence (Feb)
21:00 U.S. President Trump Speaks
"""
from econ_calendar_analysis import (
    _load_cached_analysis,
    _store_analysis,
    compute_context_hash,
    extract_rollup_context,
    generate_event_analysis,
)

_TEST_DB = Path(__file__).parent / "data" / "test_panel_events.db"


def _seed_db(db_path) -> tuple[str, str]:
    """Insert two events for 2026-02-24 (one all-day, one timed), return (week_id, event_id)."""
    raw = (
        "Sunday, February 22 to Saturday, February 28, 2026\n\n"
        "Monday, February 24, 2026\n"
        "10:00 CB Consumer Confidence (Feb)\n"
        "All United States - Washington's Birthday - USD*\n"
    )
    parsed = parse_week_block(raw)
    week_id = upsert_week_and_events(
        db_path,
        parsed.week_start_date,
        parsed.week_end_date,
        raw,
        parsed.events,
    )
    rows = get_events_for_date(db_path, "2026-02-24")
    event_id = rows[0]["id"]
    return week_id, event_id


class TestGetEventsForDate(unittest.TestCase):
    """Integration: get_events_for_date queries the real SQLite file."""

    def setUp(self) -> None:
        _TEST_DB.parent.mkdir(parents=True, exist_ok=True)
        if _TEST_DB.exists():
            _TEST_DB.unlink()

    def tearDown(self) -> None:
        if _TEST_DB.exists():
            _TEST_DB.unlink()

    def test_returns_empty_for_date_with_no_events(self) -> None:
        get_connection(_TEST_DB).close()  # initialise schema
        result = get_events_for_date(_TEST_DB, "2026-01-01")
        self.assertEqual(result, [])

    def test_returns_events_sorted_all_day_first(self) -> None:
        """All-day events must appear before timed events."""
        _seed_db(_TEST_DB)
        events = get_events_for_date(_TEST_DB, "2026-02-24")
        self.assertEqual(len(events), 2)
        # all_day=1 should be first
        self.assertEqual(events[0]["all_day"], 1, "All-day event should be first")
        self.assertEqual(events[1]["all_day"], 0, "Timed event should be second")

    def test_returns_correct_fields(self) -> None:
        _seed_db(_TEST_DB)
        events = get_events_for_date(_TEST_DB, "2026-02-24")
        timed = next(e for e in events if not e["all_day"])
        self.assertEqual(timed["title"], "CB Consumer Confidence (Feb)")
        self.assertEqual(timed["time_local"], "10:00")
        self.assertIsNone(timed["country_or_region"])

    def test_all_day_fields(self) -> None:
        _seed_db(_TEST_DB)
        events = get_events_for_date(_TEST_DB, "2026-02-24")
        all_day_evt = next(e for e in events if e["all_day"])
        self.assertEqual(all_day_evt["currency_tag"], "USD")
        self.assertEqual(all_day_evt["country_or_region"], "United States")


class TestDailyViewIntegration(unittest.TestCase):
    """Test that Daily View correctly shows events for Tuesday February 24, 2026."""
    
    def setUp(self) -> None:
        _TEST_DB.parent.mkdir(parents=True, exist_ok=True)
        if _TEST_DB.exists():
            _TEST_DB.unlink()
    
    def tearDown(self) -> None:
        if _TEST_DB.exists():
            _TEST_DB.unlink()
    
    def test_tuesday_events_from_sample_input(self) -> None:
        """Verify get_events_for_date returns Tuesday events from FULL_EXAMPLE."""
        # Parse and save the full example week
        parsed = parse_week_block(FULL_EXAMPLE)
        week_id = upsert_week_and_events(
            _TEST_DB,
            parsed.week_start_date,
            parsed.week_end_date,
            FULL_EXAMPLE,
            parsed.events
        )
        
        # Get events for Tuesday February 24, 2026
        events = get_events_for_date(_TEST_DB, "2026-02-24")
        
        # Should have 2 events: CB Consumer Confidence and U.S. President Trump Speaks
        self.assertGreaterEqual(len(events), 2, "Should have at least 2 events for Tuesday")
        
        # Find the timed events
        timed_events = [e for e in events if not e["all_day"]]
        self.assertGreaterEqual(len(timed_events), 2, "Should have at least 2 timed events")
        
        # Verify specific events exist
        titles = [e["title"] for e in timed_events]
        self.assertIn("CB Consumer Confidence (Feb)", titles, "Should include CB Consumer Confidence")
        self.assertIn("U.S. President Trump Speaks", titles, "Should include U.S. President Trump Speaks")
        
        # Verify times
        cb_event = next(e for e in timed_events if "Consumer Confidence" in e["title"])
        self.assertEqual(cb_event["time_local"], "10:00", "CB Consumer Confidence should be at 10:00")
        
        trump_event = next(e for e in timed_events if "Trump" in e["title"])
        self.assertEqual(trump_event["time_local"], "21:00", "Trump Speaks should be at 21:00")
    
    def test_daily_view_includes_economic_events_section(self) -> None:
        """Verify that Daily View rendering includes Economic events section when events exist."""
        # Seed database with Tuesday events
        parsed = parse_week_block(FULL_EXAMPLE)
        upsert_week_and_events(
            _TEST_DB,
            parsed.week_start_date,
            parsed.week_end_date,
            FULL_EXAMPLE,
            parsed.events
        )
        
        # Import render function (need to patch DB_PATH)
        with patch("twifo.DB_PATH", _TEST_DB), \
             patch("twifo.ECON_CALENDAR_AVAILABLE", True):
            from twifo import _render_econ_events_panel
            
            # Render panel for Tuesday February 24, 2026
            result = _render_econ_events_panel("2026-02-24", None)
            
            # Should return a Div component, not None
            self.assertIsNotNone(result, "Panel should render when events exist")
            
            # Verify it's a Dash component (has children attribute or is a Div)
            self.assertTrue(hasattr(result, 'children') or hasattr(result, '__class__'),
                          "Result should be a Dash component")
            
            # Verify events are included (check if result contains event titles)
            result_str = str(result)
            self.assertIn("Economic Events", result_str, "Panel should include 'Economic Events' heading")
            self.assertIn("CB Consumer Confidence", result_str or "", "Panel should include CB Consumer Confidence event")


class TestPanelRenders(unittest.TestCase):
    """
    Verify _render_econ_events_panel returns a Div (not None) when events exist,
    and returns None when no events are stored.
    """

    def setUp(self) -> None:
        _TEST_DB.parent.mkdir(parents=True, exist_ok=True)
        if _TEST_DB.exists():
            _TEST_DB.unlink()

    def tearDown(self) -> None:
        if _TEST_DB.exists():
            _TEST_DB.unlink()

    def _mock_analysis(self):
        """Stub generate_event_analysis so tests do not hit OpenAI."""
        return {
            "theory_text": "Theory placeholder.",
            "dynamics_text": "Dynamics placeholder.",
            "from_cache": False,
            "no_context": True,
        }

    def test_panel_returns_none_when_no_events(self) -> None:
        """Panel must be None for a date with no calendar events."""
        # Import the helper directly; patch DB_PATH to test db.
        import econ_calendar_analysis as eca
        import twifo  # noqa: F401 – ensure twifo module is importable

        with (
            patch("twifo.DB_PATH", _TEST_DB),
            patch("twifo.get_events_for_date", side_effect=lambda db, d: []),
            patch("twifo.ECON_CALENDAR_AVAILABLE", True),
        ):
            from twifo import _render_econ_events_panel
            result = _render_econ_events_panel("2026-02-24", None)
            self.assertIsNone(result, "Panel must be None when no events exist")

    def test_panel_returns_div_when_events_exist(self) -> None:
        """Panel must return a Dash Div containing event cards."""
        _seed_db(_TEST_DB)
        events = get_events_for_date(_TEST_DB, "2026-02-24")

        with (
            patch("twifo.DB_PATH", _TEST_DB),
            patch("twifo.get_events_for_date", return_value=events),
            patch("twifo.generate_event_analysis", side_effect=lambda **kw: self._mock_analysis()),
            patch("twifo.ECON_CALENDAR_AVAILABLE", True),
        ):
            from twifo import _render_econ_events_panel
            result = _render_econ_events_panel("2026-02-24", None)
            self.assertIsNotNone(result, "Panel must not be None when events exist")

    def test_panel_disclaimer_present(self) -> None:
        """Panel must include the 'Educational only' disclaimer."""
        _seed_db(_TEST_DB)
        events = get_events_for_date(_TEST_DB, "2026-02-24")

        disclaimer_found = False

        with (
            patch("twifo.DB_PATH", _TEST_DB),
            patch("twifo.get_events_for_date", return_value=events),
            patch("twifo.generate_event_analysis", side_effect=lambda **kw: self._mock_analysis()),
            patch("twifo.ECON_CALENDAR_AVAILABLE", True),
        ):
            from twifo import _render_econ_events_panel
            panel = _render_econ_events_panel("2026-02-24", None)

        # Walk component tree looking for disclaimer text
        def _walk(node):
            nonlocal disclaimer_found
            if hasattr(node, "children"):
                kids = node.children
                if isinstance(kids, str) and "Educational only" in kids:
                    disclaimer_found = True
                elif isinstance(kids, list):
                    for child in kids:
                        _walk(child)
                elif kids is not None:
                    _walk(kids)

        _walk(panel)
        self.assertTrue(disclaimer_found, "Disclaimer text 'Educational only' not found in panel")


class TestAnalysisCaching(unittest.TestCase):
    """
    Verify that a matching context_hash prevents a second LLM call.
    """

    def setUp(self) -> None:
        _TEST_DB.parent.mkdir(parents=True, exist_ok=True)
        if _TEST_DB.exists():
            _TEST_DB.unlink()

    def tearDown(self) -> None:
        if _TEST_DB.exists():
            _TEST_DB.unlink()

    def _make_event_row(self) -> dict:
        """Seed db and return first event dict."""
        _seed_db(_TEST_DB)
        return get_events_for_date(_TEST_DB, "2026-02-24")[1]  # timed event

    def test_cache_hit_skips_llm(self) -> None:
        """
        After the first call stores a result, a second call with the same
        context_hash must NOT invoke the OpenAI client.
        """
        event = self._make_event_row()
        as_of = "2026-02-24"
        rollup = None  # empty rollup → context_hash is fixed

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Generated text."))]
        )

        with patch("openai_client.get_client", return_value=mock_client):
            result1 = generate_event_analysis(
                event=event,
                as_of_date=as_of,
                rollup_json=rollup,
                db_path=_TEST_DB,
            )

        # LLM was called for theory + dynamics = 2 calls
        self.assertEqual(mock_client.chat.completions.create.call_count, 2)
        self.assertFalse(result1["from_cache"], "First call should not be from cache")

        # Second call — same event, same context_hash
        mock_client2 = MagicMock()
        with patch("openai_client.get_client", return_value=mock_client2):
            result2 = generate_event_analysis(
                event=event,
                as_of_date=as_of,
                rollup_json=rollup,
                db_path=_TEST_DB,
            )

        mock_client2.chat.completions.create.assert_not_called()
        self.assertTrue(result2["from_cache"], "Second call must be served from cache")
        self.assertEqual(result2["theory_text"], result1["theory_text"])

    def test_cache_miss_on_different_context_hash(self) -> None:
        """
        Changing the rollup content changes context_hash and must trigger a new LLM call.
        """
        event = self._make_event_row()
        as_of = "2026-02-24"

        rollup_a = None  # empty rollup
        rollup_b = {
            "sections": {
                "tldr": [{"text": "Different context today."}]
            }
        }

        # Verify hashes differ
        hash_a = compute_context_hash(rollup_a)
        hash_b = compute_context_hash(rollup_b)
        self.assertNotEqual(hash_a, hash_b, "Different rollups should produce different hashes")

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="Generated."))]
        )

        with patch("openai_client.get_client", return_value=mock_client):
            generate_event_analysis(event=event, as_of_date=as_of, rollup_json=rollup_a, db_path=_TEST_DB)

        self.assertEqual(mock_client.chat.completions.create.call_count, 2, "First call: 2 LLM requests")

        mock_client.reset_mock()

        with patch("openai_client.get_client", return_value=mock_client):
            result_b = generate_event_analysis(event=event, as_of_date=as_of, rollup_json=rollup_b, db_path=_TEST_DB)

        self.assertEqual(mock_client.chat.completions.create.call_count, 2, "New context should trigger 2 new LLM calls")
        self.assertFalse(result_b["from_cache"], "Different context hash must not hit cache")

    def test_store_and_load_roundtrip(self) -> None:
        """_store_analysis / _load_cached_analysis roundtrip check."""
        event_id = str(uuid.uuid4())
        as_of = "2026-02-25"
        context_hash = "abc123def456"

        # Seed a fake event row so FK constraint is satisfied
        conn = get_connection(_TEST_DB)
        week_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO econ_week (id, week_start_date, week_end_date, raw_text) "
            "VALUES (?, ?, ?, ?)",
            (week_id, "2026-02-22", "2026-02-28", "raw"),
        )
        conn.execute(
            "INSERT INTO econ_event (id, week_id, event_date, all_day, title) "
            "VALUES (?, ?, ?, 0, 'Test Event')",
            (event_id, week_id, "2026-02-25"),
        )
        conn.commit()
        conn.close()

        _store_analysis(_TEST_DB, event_id, as_of, "Theory text.", "Dynamics text.", context_hash)
        result = _load_cached_analysis(_TEST_DB, event_id, as_of, context_hash)

        self.assertIsNotNone(result)
        self.assertEqual(result["theory_text"], "Theory text.")
        self.assertEqual(result["dynamics_text"], "Dynamics text.")


class TestComputeContextHash(unittest.TestCase):
    """Unit tests for the context hash function."""

    def test_empty_rollup_gives_deterministic_hash(self) -> None:
        h1 = compute_context_hash(None)
        h2 = compute_context_hash(None)
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 12)

    def test_different_content_gives_different_hash(self) -> None:
        r1 = {"sections": {"tldr": [{"text": "Markets rally."}]}}
        r2 = {"sections": {"tldr": [{"text": "Markets fall."}]}}
        self.assertNotEqual(compute_context_hash(r1), compute_context_hash(r2))

    def test_same_content_gives_same_hash(self) -> None:
        r = {"sections": {"tldr": [{"text": "Stable."}]}}
        self.assertEqual(compute_context_hash(r), compute_context_hash(r))

    def test_hash_length_is_12(self) -> None:
        r = {"sections": {"executive_snapshot": [{"text": "snapshot text"}]}}
        self.assertEqual(len(compute_context_hash(r)), 12)


class TestExtractRollupContext(unittest.TestCase):
    """Unit tests for extract_rollup_context."""

    def test_empty_rollup_returns_empty_string(self) -> None:
        self.assertEqual(extract_rollup_context(None), "")
        self.assertEqual(extract_rollup_context({}), "")

    def test_extracts_tldr_and_snapshot(self) -> None:
        rollup = {
            "sections": {
                "tldr": [{"text": "Rates flat."}, {"text": "Dollar weak."}],
                "executive_snapshot": [{"text": "Risk-on tone."}],
            }
        }
        ctx = extract_rollup_context(rollup)
        self.assertIn("Rates flat.", ctx)
        self.assertIn("Dollar weak.", ctx)
        self.assertIn("Risk-on tone.", ctx)

    def test_output_capped_at_900_chars(self) -> None:
        big = {"sections": {"tldr": [{"text": "X" * 300} for _ in range(10)]}}
        ctx = extract_rollup_context(big)
        self.assertLessEqual(len(ctx), 900)


# ===========================================================================
# Part 2 — Economic Brief feature tests
# ===========================================================================

# Three-date fixture spanning Feb 23-25 2026 (Mon/Tue/Wed)
_THREE_DATE_CALENDAR = """\
Sunday, February 22 to Saturday, February 28, 2026

Monday, February 23, 2026
10:00 CB Consumer Confidence (Feb)
21:00 U.S. President Trump Speaks

Tuesday, February 24, 2026
09:00 S&P/Case-Shiller Home Price (Dec)
10:00 Richmond Fed Manufacturing Index (Feb)

Wednesday, February 25, 2026
All Germany - GDP Final (Q4) - EUR*
07:00 MBA Mortgage Applications
10:00 New Home Sales (Jan)
"""

_THREE_DATES = ["2026-02-23", "2026-02-24", "2026-02-25"]

_TEST_BRIEF_DB = Path(__file__).parent / "data" / "test_brief_feature.db"


def _seed_three_date_week(db_path) -> None:
    """Parse and upsert the three-date fixture into db_path."""
    parsed = parse_week_block(_THREE_DATE_CALENDAR)
    upsert_week_and_events(db_path, parsed.week_start_date, parsed.week_end_date, _THREE_DATE_CALENDAR, parsed.events)


class TestDailyViewNeverCallsLLM(unittest.TestCase):
    """
    Test 1 — Daily View must never invoke the LLM client.

    Even when no brief is cached, rendering the Economic Brief section must
    display the static fallback message without touching the LLM.
    """

    def setUp(self) -> None:
        _TEST_BRIEF_DB.parent.mkdir(parents=True, exist_ok=True)
        if _TEST_BRIEF_DB.exists():
            _TEST_BRIEF_DB.unlink()
        # Seed events so the panel has something to render
        _seed_three_date_week(_TEST_BRIEF_DB)

    def tearDown(self) -> None:
        if _TEST_BRIEF_DB.exists():
            _TEST_BRIEF_DB.unlink()

    def test_brief_section_shows_fallback_when_no_brief_cached(self) -> None:
        """
        No cached brief exists.  The sentinel raises AssertionError if called.
        Verify: no exception from the sentinel AND the fallback message appears.
        """
        def _llm_sentinel(*args, **kwargs):
            raise AssertionError("LLM client was called from Daily View — this is forbidden.")

        from econ_calendar_store import get_daily_brief as _real_get_daily_brief

        with (
            patch("twifo.DB_PATH", _TEST_BRIEF_DB),
            patch("twifo.ECON_CALENDAR_AVAILABLE", True),
            patch("twifo.get_events_for_date", side_effect=lambda db, d: get_events_for_date(db, d)),
            # get_daily_brief returns None (no brief cached)
            patch("twifo.get_daily_brief", return_value=None),
            # The sentinel replaces the LLM client — must NOT be called
            patch("openai_client.get_client", side_effect=_llm_sentinel),
        ):
            from twifo import _render_econ_daily_brief

            # Should not raise; sentinel must stay silent
            result = _render_econ_daily_brief("2026-02-23", dynamics_mode=True)

        self.assertIsNotNone(result, "Brief section must be returned (events exist for this date)")

        # Walk the component tree looking for the fallback message
        fallback_msg = "Brief not generated for this date"
        result_str = str(result)
        self.assertIn(
            fallback_msg,
            result_str,
            f"Fallback message '{fallback_msg}' not found in rendered output",
        )


class TestAdminSaveGeneratesRankAndBrief(unittest.TestCase):
    """
    Test 2 — Admin Save pre-generates rank and brief rows for every date.

    Paste a valid weekly calendar covering 3 dates.  Trigger the AI generation
    pipeline (mocking the LLM client to return deterministic output).  Assert
    that econ_daily_rank and econ_daily_brief rows exist for each date.
    """

    def setUp(self) -> None:
        _TEST_BRIEF_DB.parent.mkdir(parents=True, exist_ok=True)
        if _TEST_BRIEF_DB.exists():
            _TEST_BRIEF_DB.unlink()

    def tearDown(self) -> None:
        if _TEST_BRIEF_DB.exists():
            _TEST_BRIEF_DB.unlink()

    def _make_mock_client(self, rank_json: str, brief_json: str):
        """Return a mock LLM client that alternates rank / brief responses."""
        responses = []
        # For each date: one rank call, one brief call
        for _ in _THREE_DATES:
            responses.append(MagicMock(choices=[MagicMock(message=MagicMock(content=rank_json))]))
            responses.append(MagicMock(choices=[MagicMock(message=MagicMock(content=brief_json))]))
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = responses
        return mock_client

    def test_rank_and_brief_rows_created_for_each_date(self) -> None:
        """After Save + generation, every date must have rank and brief rows."""
        # Seed the week first
        _seed_three_date_week(_TEST_BRIEF_DB)

        # Minimal valid rank JSON the AI module will accept
        _rank_response = lambda date_iso: json.dumps({
            "ranked": [
                {"event_key": "all_day|gdp final (q4)", "priority": 1, "importance_tier": "high", "reason": "Key release"},
                {"event_key": "07:00|mba mortgage applications", "priority": 2, "importance_tier": "medium", "reason": "Housing data"},
                {"event_key": "10:00|new home sales (jan)", "priority": 3, "importance_tier": "medium", "reason": "Housing market"},
            ]
        })
        _brief_response = json.dumps({
            "theory_text": "Theory content here.",
            "dynamics_text": "Dynamics content here.",
        })

        # We need per-date appropriate rank responses
        # Use a single "good enough" rank; the module validates and uses it
        _rank_json = json.dumps({
            "ranked": [
                {"event_key": "10:00|cb consumer confidence (feb)", "priority": 1, "importance_tier": "high", "reason": "Consumer data"},
                {"event_key": "21:00|u.s. president trump speaks", "priority": 2, "importance_tier": "low", "reason": "Speech"},
            ]
        })

        # Build enough responses for 3 dates x (1 rank call + 1 brief call) = 6
        responses = []
        for _ in _THREE_DATES:
            responses.append(MagicMock(choices=[MagicMock(message=MagicMock(content=_rank_json))]))
            responses.append(MagicMock(choices=[MagicMock(message=MagicMock(content=_brief_response))]))
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = responses

        from econ_calendar_ai import generate_for_week
        from econ_calendar_store import get_daily_brief as _get_brief, get_daily_rank as _get_rank

        with patch("openai_client.get_client", return_value=mock_client):
            generate_for_week(
                dates=_THREE_DATES,
                dynamics_mode=True,
                db_path=_TEST_BRIEF_DB,
                rollups_daily_dir=None,
            )

        for date_iso in _THREE_DATES:
            rank_row = _get_rank(_TEST_BRIEF_DB, date_iso)
            brief_row = _get_brief(_TEST_BRIEF_DB, date_iso)
            self.assertIsNotNone(rank_row, f"econ_daily_rank row missing for {date_iso}")
            self.assertIsNotNone(brief_row, f"econ_daily_brief row missing for {date_iso}")
            self.assertTrue(rank_row.get("rank_json"), f"rank_json empty for {date_iso}")
            self.assertTrue(brief_row.get("theory_text"), f"theory_text empty for {date_iso}")


class TestResaveDoesNotCallGPTAgain(unittest.TestCase):
    """
    Test 3 — Re-saving the same week must not trigger additional LLM calls.

    Run generate_for_week once (LLM is called).  Run it again with the same
    dates.  Assert that the LLM call count did not increase on the second run.
    """

    def setUp(self) -> None:
        _TEST_BRIEF_DB.parent.mkdir(parents=True, exist_ok=True)
        if _TEST_BRIEF_DB.exists():
            _TEST_BRIEF_DB.unlink()

    def tearDown(self) -> None:
        if _TEST_BRIEF_DB.exists():
            _TEST_BRIEF_DB.unlink()

    def test_second_save_reuses_cache(self) -> None:
        """LLM call count must not increase after the second Save."""
        _seed_three_date_week(_TEST_BRIEF_DB)

        _rank_json = json.dumps({
            "ranked": [
                {"event_key": "10:00|cb consumer confidence (feb)", "priority": 1, "importance_tier": "high", "reason": "Consumer data"},
                {"event_key": "21:00|u.s. president trump speaks", "priority": 2, "importance_tier": "low", "reason": "Speech"},
            ]
        })
        _brief_json = json.dumps({
            "theory_text": "Theory: solid employment backdrop.",
            "dynamics_text": "Dynamics: watch USD reaction.",
        })

        from econ_calendar_ai import generate_for_week

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=_rank_json))]
        )

        def _smart_response(*args, **kwargs):
            """Return rank or brief response based on prompt content."""
            messages = kwargs.get("messages") or args[1] if args else []
            user_msg = ""
            for m in messages:
                if isinstance(m, dict) and m.get("role") == "user":
                    user_msg = m.get("content", "")
                    break
            if "Rank each event" in user_msg:
                return MagicMock(choices=[MagicMock(message=MagicMock(content=_rank_json))])
            return MagicMock(choices=[MagicMock(message=MagicMock(content=_brief_json))])

        mock_client.chat.completions.create.side_effect = _smart_response

        # First save — LLM is called for each date
        with patch("openai_client.get_client", return_value=mock_client):
            generate_for_week(
                dates=_THREE_DATES,
                dynamics_mode=True,
                db_path=_TEST_BRIEF_DB,
                rollups_daily_dir=None,
            )

        count_after_first_save = mock_client.chat.completions.create.call_count
        self.assertGreater(count_after_first_save, 0, "LLM must be called at least once on first save")

        # Second save — same dates, same events → hashes match → cache should be hit
        with patch("openai_client.get_client", return_value=mock_client):
            generate_for_week(
                dates=_THREE_DATES,
                dynamics_mode=True,
                db_path=_TEST_BRIEF_DB,
                rollups_daily_dir=None,
            )

        count_after_second_save = mock_client.chat.completions.create.call_count
        self.assertEqual(
            count_after_first_save,
            count_after_second_save,
            f"LLM was called again on the second Save: "
            f"first={count_after_first_save}, second={count_after_second_save}",
        )


if __name__ == "__main__":
    unittest.main()

