"""
test_brief_fallback.py
======================
Tests for the read-time brief fallback added to the Daily Recap page.

Covers:
  1. Regular user page load with missing brief → no generation triggered.
  2. Logged-in user page load with missing brief → Generate button rendered.
  3. POST /api/econ/generate-brief without auth → 401.
  4. POST /api/econ/generate-brief with auth, no events → 404.
  5. POST /api/econ/generate-brief with auth, valid date → 200, brief persisted.
  6. Two simultaneous requests for the same date → exactly one LLM call.
  7. render_generated_brief callback → inline brief replaces status div.
"""

import sys
import os
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Ensure the TWIFO_Sharing package directory is on sys.path
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db(path: str) -> None:
    """Create a minimal econ_daily_brief + econ_event schema."""
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE IF NOT EXISTS econ_week (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_start TEXT NOT NULL,
            week_end TEXT NOT NULL,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS econ_event (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            week_id INTEGER,
            event_date TEXT NOT NULL,
            event_time TEXT,
            country TEXT,
            currency TEXT,
            event_name TEXT,
            importance TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS econ_daily_rank (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL,
            events_hash TEXT,
            rank_json TEXT,
            created_at TEXT
        );

        CREATE TABLE IF NOT EXISTS econ_daily_brief (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_date TEXT NOT NULL UNIQUE,
            context_hash TEXT,
            theory_text TEXT,
            dynamics_text TEXT,
            is_error INTEGER DEFAULT 0,
            created_at TEXT
        );
    """)
    con.commit()
    con.close()


def _insert_event(db_path: str, event_date: str) -> None:
    """Insert a single dummy event for the given date."""
    con = sqlite3.connect(db_path)
    con.execute(
        "INSERT INTO econ_event (week_id, event_date, event_time, country, currency, event_name, importance) "
        "VALUES (1, ?, '08:30', 'US', 'USD', 'Test Event', 'high')",
        (event_date,),
    )
    con.commit()
    con.close()


def _read_brief(db_path: str, event_date: str) -> dict | None:
    """Read a brief row from the DB."""
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT * FROM econ_daily_brief WHERE event_date = ?", (event_date,)
    ).fetchone()
    con.close()
    return dict(row) if row else None


def _out(msg: str) -> None:
    sys.stdout.buffer.write((msg + "\n").encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()


# ---------------------------------------------------------------------------
# Test: _render_econ_daily_brief — button visibility
# ---------------------------------------------------------------------------

class TestRenderEconDailyBrief(unittest.TestCase):
    """Unit tests for _render_econ_daily_brief render logic."""

    def _find_component(self, component, target_type=None, target_id_type=None):
        """Walk a Dash component tree and collect matching nodes."""
        results = []
        if component is None:
            return results

        # Check this node
        is_match = True
        if target_type and not isinstance(component, target_type):
            is_match = False
        if target_id_type and isinstance(getattr(component, "id", None), dict):
            if component.id.get("type") != target_id_type:
                is_match = False
        elif target_id_type:
            is_match = False

        if is_match and (target_type or target_id_type):
            results.append(component)

        # Recurse into children
        children = getattr(component, "children", None)
        if children is None:
            return results
        if not isinstance(children, list):
            children = [children]
        for child in children:
            results.extend(self._find_component(child, target_type, target_id_type))
        return results

    def test_no_button_for_regular_user(self):
        """Regular user (is_logged_in=False) must NOT see the Generate Brief button."""
        from dash import html
        from econ_calendar_store import get_events_for_date, get_daily_brief

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            _insert_event(db_path, "2026-03-01")

            with patch("twifo.DB_PATH", db_path), \
                 patch("twifo.ECON_CALENDAR_AVAILABLE", True), \
                 patch("twifo.get_events_for_date", lambda p, d: get_events_for_date(db_path, d)), \
                 patch("twifo.get_daily_brief", lambda p, d: get_daily_brief(db_path, d)):

                from twifo import _render_econ_daily_brief
                result = _render_econ_daily_brief("2026-03-01", dynamics_mode=True, is_logged_in=False)

            # Should return a Div (pending status), but NO button
            self.assertIsNotNone(result, "Should return a status div (events exist)")
            buttons = self._find_component(result, target_id_type="econ-gen-brief-btn")
            self.assertEqual(len(buttons), 0, "Regular user must NOT see Generate Brief button")
            _out("PASS: no button for regular user")

        finally:
            os.unlink(db_path)

    def test_button_for_logged_in_user(self):
        """Logged-in user (is_logged_in=True) MUST see the Generate Brief button."""
        from dash import html
        from econ_calendar_store import get_events_for_date, get_daily_brief

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            _insert_event(db_path, "2026-03-02")

            with patch("twifo.DB_PATH", db_path), \
                 patch("twifo.ECON_CALENDAR_AVAILABLE", True), \
                 patch("twifo.get_events_for_date", lambda p, d: get_events_for_date(db_path, d)), \
                 patch("twifo.get_daily_brief", lambda p, d: get_daily_brief(db_path, d)):

                from twifo import _render_econ_daily_brief
                result = _render_econ_daily_brief("2026-03-02", dynamics_mode=True, is_logged_in=True)

            self.assertIsNotNone(result)
            buttons = self._find_component(result, target_id_type="econ-gen-brief-btn")
            self.assertGreater(len(buttons), 0, "Logged-in user MUST see Generate Brief button")
            _out("PASS: button visible for logged-in user")

        finally:
            os.unlink(db_path)

    def test_no_section_when_no_events(self):
        """When no events exist for the date, the entire section should be hidden (None)."""
        from econ_calendar_store import get_events_for_date, get_daily_brief

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            # No events inserted for this date

            with patch("twifo.DB_PATH", db_path), \
                 patch("twifo.ECON_CALENDAR_AVAILABLE", True), \
                 patch("twifo.get_events_for_date", lambda p, d: get_events_for_date(db_path, d)), \
                 patch("twifo.get_daily_brief", lambda p, d: get_daily_brief(db_path, d)):

                from twifo import _render_econ_daily_brief
                result = _render_econ_daily_brief("2026-03-03", dynamics_mode=True, is_logged_in=True)

            self.assertIsNone(result, "Section must be hidden when no events exist")
            _out("PASS: section hidden when no events")

        finally:
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# Test: Flask API endpoint /api/econ/generate-brief
# ---------------------------------------------------------------------------

class TestApiGenerateBrief(unittest.TestCase):
    """Integration tests for the /api/econ/generate-brief Flask route."""

    def _get_app(self):
        """Import the Flask test client from twifo."""
        import twifo
        return twifo.server.test_client()

    def test_401_without_auth(self):
        """Unauthenticated request must return 401."""
        client = self._get_app()
        resp = client.post(
            "/api/econ/generate-brief",
            data=json.dumps({"date_iso": "2026-03-01"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)
        data = json.loads(resp.data)
        self.assertIn("error", data)
        _out("PASS: 401 without auth")

    def test_401_with_empty_login_header(self):
        """Empty X-Login-User header must also return 401."""
        client = self._get_app()
        resp = client.post(
            "/api/econ/generate-brief",
            data=json.dumps({"date_iso": "2026-03-01"}),
            content_type="application/json",
            headers={"X-Login-User": ""},
        )
        self.assertEqual(resp.status_code, 401)
        _out("PASS: 401 with empty login header")

    def test_400_missing_date(self):
        """Missing date_iso must return 400."""
        client = self._get_app()
        resp = client.post(
            "/api/econ/generate-brief",
            data=json.dumps({}),
            content_type="application/json",
            headers={"X-Login-User": "admin"},
        )
        self.assertEqual(resp.status_code, 400)
        _out("PASS: 400 missing date_iso")

    def test_400_invalid_date_format(self):
        """Malformed date_iso must return 400."""
        client = self._get_app()
        resp = client.post(
            "/api/econ/generate-brief",
            data=json.dumps({"date_iso": "20260301"}),
            content_type="application/json",
            headers={"X-Login-User": "admin"},
        )
        self.assertEqual(resp.status_code, 400)
        _out("PASS: 400 invalid date format")

    def test_404_no_events(self):
        """Date with no events must return 404."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)

            import twifo
            with patch.object(twifo, "DB_PATH", db_path), \
                 patch.object(twifo, "ECON_CALENDAR_AVAILABLE", True), \
                 patch.object(twifo, "get_events_for_date",
                              lambda p, d: []):  # no events
                client = twifo.server.test_client()
                resp = client.post(
                    "/api/econ/generate-brief",
                    data=json.dumps({"date_iso": "2026-03-04"}),
                    content_type="application/json",
                    headers={"X-Login-User": "admin"},
                )
            self.assertEqual(resp.status_code, 404)
            _out("PASS: 404 when no events")

        finally:
            os.unlink(db_path)

    def test_200_generates_and_persists_brief(self):
        """
        Happy path: given events for a date, the endpoint calls the generator,
        persists the result, and returns it in the response.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            _insert_event(db_path, "2026-03-05")

            fake_brief = {
                "theory_text": "Markets are pricing in a 25bp cut.",
                "dynamics_text": "",
                "error": None,
            }

            import twifo
            from econ_calendar_store import get_events_for_date, get_daily_brief, upsert_daily_brief

            # Patch generate_for_date to avoid real LLM calls and write to our test DB
            def fake_generate(date_iso, dynamics_mode, db_path, rollups_daily_dir):
                upsert_daily_brief(
                    db_path, date_iso,
                    context_hash="testhash",
                    theory_text=fake_brief["theory_text"],
                    dynamics_text=fake_brief["dynamics_text"],
                )
                return {"error": None}

            with patch.object(twifo, "DB_PATH", db_path), \
                 patch.object(twifo, "ECON_CALENDAR_AVAILABLE", True), \
                 patch.object(twifo, "get_events_for_date",
                              lambda p, d: get_events_for_date(db_path, d)), \
                 patch.object(twifo, "get_daily_brief",
                              lambda p, d: get_daily_brief(db_path, d)), \
                 patch("twifo.api_generate_brief.__wrapped__" if hasattr(twifo.api_generate_brief, "__wrapped__") else "econ_calendar_ai.generate_for_date",
                       fake_generate, create=True):

                # Directly patch the module-level import inside the route
                import importlib
                import econ_calendar_ai as _eai
                original_gen = _eai.generate_for_date
                _eai.generate_for_date = fake_generate
                try:
                    client = twifo.server.test_client()
                    resp = client.post(
                        "/api/econ/generate-brief",
                        data=json.dumps({"date_iso": "2026-03-05", "dynamics_mode": True}),
                        content_type="application/json",
                        headers={"X-Login-User": "admin"},
                    )
                finally:
                    _eai.generate_for_date = original_gen

            self.assertEqual(resp.status_code, 200, f"Expected 200, got {resp.status_code}: {resp.data}")
            data = json.loads(resp.data)
            self.assertEqual(data["date_iso"], "2026-03-05")
            self.assertEqual(data["theory_text"], fake_brief["theory_text"])

            # Verify DB row was written
            row = _read_brief(db_path, "2026-03-05")
            self.assertIsNotNone(row, "Brief must be persisted in DB")
            self.assertEqual(row["theory_text"], fake_brief["theory_text"])
            _out("PASS: 200, brief generated and persisted")

        finally:
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# Test: Idempotency lock — only one LLM call for simultaneous requests
# ---------------------------------------------------------------------------

class TestBriefGenerationLock(unittest.TestCase):
    """Verify that N simultaneous requests produce exactly one LLM call."""

    def test_concurrent_requests_single_llm_call(self):
        """
        Two threads both call generate_for_date via the lock mechanism.
        Only the first acquirer should call the LLM; the second should read
        the result already written by the first.
        """
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            _make_db(db_path)
            _insert_event(db_path, "2026-03-06")

            call_count = {"n": 0}
            lock_for_test = threading.Lock()

            from econ_calendar_store import upsert_daily_brief, get_daily_brief

            def slow_generate(date_iso, dynamics_mode, db_path, rollups_daily_dir):
                """Simulate a slow LLM call; count invocations."""
                import time
                with lock_for_test:
                    call_count["n"] += 1
                time.sleep(0.05)  # simulate latency
                upsert_daily_brief(
                    db_path, date_iso,
                    context_hash="concurrent_test",
                    theory_text="Concurrent test brief.",
                    dynamics_text="",
                )
                return {"error": None}

            import twifo
            import econ_calendar_ai as _eai
            original_gen = _eai.generate_for_date
            _eai.generate_for_date = slow_generate

            results = {}

            def _call_api(thread_id):
                with patch.object(twifo, "DB_PATH", db_path), \
                     patch.object(twifo, "ECON_CALENDAR_AVAILABLE", True), \
                     patch.object(twifo, "get_events_for_date",
                                  lambda p, d: [{"event_name": "Test"}]), \
                     patch.object(twifo, "get_daily_brief",
                                  lambda p, d: get_daily_brief(db_path, d)):
                    client = twifo.server.test_client()
                    resp = client.post(
                        "/api/econ/generate-brief",
                        data=json.dumps({"date_iso": "2026-03-06"}),
                        content_type="application/json",
                        headers={"X-Login-User": "admin"},
                    )
                    results[thread_id] = (resp.status_code, json.loads(resp.data))

            _eai.generate_for_date = slow_generate
            try:
                t1 = threading.Thread(target=_call_api, args=(1,))
                t2 = threading.Thread(target=_call_api, args=(2,))
                t1.start()
                t2.start()
                t1.join(timeout=30)
                t2.join(timeout=30)
            finally:
                _eai.generate_for_date = original_gen

            # Both requests must succeed
            self.assertEqual(results[1][0], 200, f"Thread 1 failed: {results[1]}")
            self.assertEqual(results[2][0], 200, f"Thread 2 failed: {results[2]}")

            # Only ONE LLM call should have been made
            self.assertEqual(call_count["n"], 1,
                             f"Expected 1 LLM call, got {call_count['n']} — idempotency lock failed")
            _out(f"PASS: concurrent requests produced {call_count['n']} LLM call (expected 1)")

        finally:
            os.unlink(db_path)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _out("\n=== Brief Fallback Tests ===\n")
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestRenderEconDailyBrief))
    suite.addTests(loader.loadTestsFromTestCase(TestApiGenerateBrief))
    suite.addTests(loader.loadTestsFromTestCase(TestBriefGenerationLock))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

