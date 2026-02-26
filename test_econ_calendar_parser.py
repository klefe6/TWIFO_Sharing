"""
Unit tests for the economic calendar parser and store.
Purpose: Validate parsing of weekly calendar text blocks and database round-trips.
Author: Kevin Lefebvre
Last Updated: 2026-02-22
"""

import os
import tempfile
import unittest

from econ_calendar_parser import parse_week_block, ParsedEvent, ParsedWeek
from econ_calendar_store import (
    upsert_week_and_events,
    get_events_for_date,
    get_weeks_in_range,
    get_week_raw_text,
)


# ── Sample text blocks ──

FULL_EXAMPLE = """\
Sunday, February 22 to Saturday, February 28, 2026

Notable Economic Data Releases

Monday, February 23, 2026
All China - Chinese New Year - CHINA*
All Japan - Emperor's Birthday - JPY*
10:00 CB Consumer Confidence (Feb)
21:00 U.S. President Trump Speaks

Tuesday, February 24, 2026
09:00 S&P/Case-Shiller Home Price (Dec)
10:00 Richmond Fed Manufacturing Index (Feb)
13:00 2-Year Note Auction

Wednesday, February 25, 2026
All Germany - GDP Final (Q4) - EUR*
07:00 MBA Mortgage Applications
10:00 New Home Sales (Jan)
10:30 Weekly EIA Crude Oil Inventories
13:00 5-Year Note Auction
"""

TIMED_ONLY = """\
Sunday, March 1 to Saturday, March 7, 2026

Monday, March 2, 2026
08:30 ISM Manufacturing PMI (Feb)
10:00 Construction Spending (Jan)
14:00 FOMC Minutes Released

Tuesday, March 3, 2026
08:30 Durable Goods Orders (Jan)
10:00 Factory Orders (Jan)
"""

MIXED_BLOCK = """\
Sunday, April 5 to Saturday, April 11, 2026

Monday, April 6, 2026
All UK - Easter Monday - GBP*
All France - Easter Monday - EUR*
08:30 Trade Balance (Feb)
10:00 ISM Non-Manufacturing PMI (Mar)

Wednesday, April 8, 2026
14:00 FOMC Meeting Minutes
"""


class TestParseWeekBlockFull(unittest.TestCase):
    """Test parsing with the full example block (all-day + timed, currencies, countries)."""

    def setUp(self) -> None:
        self.result = parse_week_block(FULL_EXAMPLE)

    def test_week_range(self) -> None:
        self.assertEqual(self.result.week_start_date, "2026-02-22")
        self.assertEqual(self.result.week_end_date, "2026-02-28")

    def test_event_count(self) -> None:
        self.assertEqual(len(self.result.events), 12)

    def test_all_day_china(self) -> None:
        evt = self.result.events[0]
        self.assertTrue(evt.all_day)
        self.assertIsNone(evt.time_local)
        self.assertEqual(evt.country_or_region, "China")
        self.assertEqual(evt.currency_tag, "CHINA")
        self.assertEqual(evt.title, "Chinese New Year")
        self.assertEqual(evt.event_date, "2026-02-23")

    def test_all_day_japan(self) -> None:
        evt = self.result.events[1]
        self.assertTrue(evt.all_day)
        self.assertEqual(evt.country_or_region, "Japan")
        self.assertEqual(evt.currency_tag, "JPY")
        self.assertEqual(evt.title, "Emperor's Birthday")

    def test_timed_cb_consumer_confidence(self) -> None:
        evt = self.result.events[2]
        self.assertFalse(evt.all_day)
        self.assertEqual(evt.time_local, "10:00")
        self.assertIsNone(evt.currency_tag)
        self.assertIsNone(evt.country_or_region)
        self.assertEqual(evt.title, "CB Consumer Confidence (Feb)")
        self.assertEqual(evt.event_date, "2026-02-23")

    def test_timed_trump_speaks(self) -> None:
        evt = self.result.events[3]
        self.assertFalse(evt.all_day)
        self.assertEqual(evt.time_local, "21:00")
        self.assertIsNone(evt.currency_tag)
        self.assertEqual(evt.event_date, "2026-02-23")

    def test_tuesday_events(self) -> None:
        tue_events = [e for e in self.result.events if e.event_date == "2026-02-24"]
        self.assertEqual(len(tue_events), 3)
        self.assertEqual(tue_events[0].time_local, "09:00")
        self.assertEqual(tue_events[1].time_local, "10:00")
        self.assertEqual(tue_events[2].time_local, "13:00")

    def test_wednesday_all_day_germany(self) -> None:
        wed_events = [e for e in self.result.events if e.event_date == "2026-02-25"]
        self.assertEqual(len(wed_events), 5)
        germany = wed_events[0]
        self.assertTrue(germany.all_day)
        self.assertEqual(germany.country_or_region, "Germany")
        self.assertEqual(germany.currency_tag, "EUR")
        self.assertEqual(germany.title, "GDP Final (Q4)")

    def test_country_not_set_for_plain_event(self) -> None:
        # "10:00 New Home Sales (Jan)" should have no country
        wed_events = [e for e in self.result.events if e.event_date == "2026-02-25"]
        new_home = [e for e in wed_events if "New Home Sales" in e.title]
        self.assertEqual(len(new_home), 1)
        self.assertIsNone(new_home[0].country_or_region)


class TestParseTimedOnly(unittest.TestCase):
    """Test a block containing only timed US events, no all-day rows."""

    def setUp(self) -> None:
        self.result = parse_week_block(TIMED_ONLY)

    def test_week_range(self) -> None:
        self.assertEqual(self.result.week_start_date, "2026-03-01")
        self.assertEqual(self.result.week_end_date, "2026-03-07")

    def test_event_count(self) -> None:
        self.assertEqual(len(self.result.events), 5)

    def test_all_events_timed(self) -> None:
        for evt in self.result.events:
            self.assertFalse(evt.all_day)
            self.assertIsNotNone(evt.time_local)

    def test_no_currency_tags(self) -> None:
        for evt in self.result.events:
            self.assertIsNone(evt.currency_tag)

    def test_specific_events(self) -> None:
        self.assertEqual(self.result.events[0].title, "ISM Manufacturing PMI (Feb)")
        self.assertEqual(self.result.events[0].time_local, "08:30")
        self.assertEqual(self.result.events[3].title, "Durable Goods Orders (Jan)")


class TestParseMixedBlock(unittest.TestCase):
    """Test a block mixing all-day and timed events."""

    def setUp(self) -> None:
        self.result = parse_week_block(MIXED_BLOCK)

    def test_week_range(self) -> None:
        self.assertEqual(self.result.week_start_date, "2026-04-05")
        self.assertEqual(self.result.week_end_date, "2026-04-11")

    def test_event_count(self) -> None:
        self.assertEqual(len(self.result.events), 5)

    def test_all_day_events(self) -> None:
        all_day = [e for e in self.result.events if e.all_day]
        self.assertEqual(len(all_day), 2)
        self.assertEqual(all_day[0].country_or_region, "UK")
        self.assertEqual(all_day[0].currency_tag, "GBP")
        self.assertEqual(all_day[1].country_or_region, "France")
        self.assertEqual(all_day[1].currency_tag, "EUR")

    def test_timed_events(self) -> None:
        timed = [e for e in self.result.events if not e.all_day]
        self.assertEqual(len(timed), 3)
        self.assertEqual(timed[0].time_local, "08:30")
        self.assertEqual(timed[1].time_local, "10:00")
        self.assertEqual(timed[2].time_local, "14:00")


class TestParserErrors(unittest.TestCase):
    """Test that error messages reference the failing line index."""

    def test_missing_week_header(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_week_block("Monday, February 23, 2026\n10:00 Some Event")
        self.assertIn("Line 0", str(ctx.exception))
        self.assertIn("Week range header not detected", str(ctx.exception))

    def test_empty_input(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            parse_week_block("")
        self.assertIn("Empty input", str(ctx.exception))

    def test_event_before_day_header(self) -> None:
        text = (
            "Sunday, February 22 to Saturday, February 28, 2026\n"
            "10:00 Orphan Event"
        )
        with self.assertRaises(ValueError) as ctx:
            parse_week_block(text)
        self.assertIn("Line 1", str(ctx.exception))
        self.assertIn("before any day header", str(ctx.exception))

    def test_invalid_event_prefix(self) -> None:
        text = (
            "Sunday, February 22 to Saturday, February 28, 2026\n"
            "Monday, February 23, 2026\n"
            "Bad line no time no all"
        )
        with self.assertRaises(ValueError) as ctx:
            parse_week_block(text)
        self.assertIn("Line 2", str(ctx.exception))
        self.assertIn("must start with 'All' or HH:MM", str(ctx.exception))


class TestStoreRoundTrip(unittest.TestCase):
    """Test database insert, query, and re-import behavior."""

    def setUp(self) -> None:
        self.tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.tmp.name
        self.tmp.close()

    def tearDown(self) -> None:
        os.unlink(self.db_path)

    def test_insert_and_query(self) -> None:
        result = parse_week_block(FULL_EXAMPLE)
        week_id = upsert_week_and_events(
            self.db_path,
            result.week_start_date,
            result.week_end_date,
            FULL_EXAMPLE,
            result.events,
        )
        self.assertIsInstance(week_id, str)

        # Query Monday events
        events = get_events_for_date(self.db_path, "2026-02-23")
        self.assertEqual(len(events), 4)
        # All-day events should appear first
        self.assertEqual(events[0]["all_day"], 1)
        self.assertEqual(events[1]["all_day"], 1)
        self.assertEqual(events[2]["all_day"], 0)

    def test_sort_order(self) -> None:
        result = parse_week_block(FULL_EXAMPLE)
        upsert_week_and_events(
            self.db_path,
            result.week_start_date,
            result.week_end_date,
            FULL_EXAMPLE,
            result.events,
        )

        events = get_events_for_date(self.db_path, "2026-02-24")
        times = [e["time_local"] for e in events]
        self.assertEqual(times, ["09:00", "10:00", "13:00"])

    def test_upsert_replaces_events(self) -> None:
        result = parse_week_block(FULL_EXAMPLE)
        week_id_1 = upsert_week_and_events(
            self.db_path,
            result.week_start_date,
            result.week_end_date,
            FULL_EXAMPLE,
            result.events,
        )

        # Re-import with fewer events (just first two)
        week_id_2 = upsert_week_and_events(
            self.db_path,
            result.week_start_date,
            result.week_end_date,
            "updated text",
            result.events[:2],
        )

        self.assertEqual(week_id_1, week_id_2)

        # Old events should be gone
        events = get_events_for_date(self.db_path, "2026-02-24")
        self.assertEqual(len(events), 0)

        # Only the two re-imported events remain
        events = get_events_for_date(self.db_path, "2026-02-23")
        self.assertEqual(len(events), 2)

    def test_get_raw_text(self) -> None:
        result = parse_week_block(FULL_EXAMPLE)
        week_id = upsert_week_and_events(
            self.db_path,
            result.week_start_date,
            result.week_end_date,
            FULL_EXAMPLE,
            result.events,
        )
        raw = get_week_raw_text(self.db_path, week_id)
        self.assertEqual(raw, FULL_EXAMPLE)

    def test_get_weeks_in_range(self) -> None:
        result = parse_week_block(FULL_EXAMPLE)
        upsert_week_and_events(
            self.db_path,
            result.week_start_date,
            result.week_end_date,
            FULL_EXAMPLE,
            result.events,
        )

        weeks = get_weeks_in_range(self.db_path, "2026-02-01", "2026-02-28")
        self.assertEqual(len(weeks), 1)
        self.assertEqual(weeks[0]["week_start_date"], "2026-02-22")

        # Out of range
        weeks = get_weeks_in_range(self.db_path, "2026-01-01", "2026-01-31")
        self.assertEqual(len(weeks), 0)

    def test_no_events_returns_empty(self) -> None:
        events = get_events_for_date(self.db_path, "2026-12-25")
        self.assertEqual(events, [])


if __name__ == "__main__":
    unittest.main()

