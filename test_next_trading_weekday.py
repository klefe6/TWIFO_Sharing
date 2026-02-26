"""
Test for _next_trading_weekday function.

Verifies that the next trading weekday is computed correctly:
- Friday → Monday
- Saturday → Monday
- Sunday → Monday
- Monday → Tuesday
- Tuesday → Wednesday
"""

import datetime as dt
from rollups import _next_trading_weekday


def test_friday_to_monday():
    """Friday should map to Monday (skip weekend)."""
    friday = dt.date(2026, 2, 27)  # Friday, Feb 27, 2026
    assert friday.weekday() == 4, "Test data error: should be Friday"
    result = _next_trading_weekday(friday)
    assert result == dt.date(2026, 3, 2), f"Expected Monday Mar 2, got {result}"
    assert result.weekday() == 0, "Result should be Monday"
    print("[PASS] Friday -> Monday")


def test_saturday_to_monday():
    """Saturday should map to Monday."""
    saturday = dt.date(2026, 2, 28)  # Saturday, Feb 28, 2026
    assert saturday.weekday() == 5, "Test data error: should be Saturday"
    result = _next_trading_weekday(saturday)
    assert result == dt.date(2026, 3, 2), f"Expected Monday Mar 2, got {result}"
    assert result.weekday() == 0, "Result should be Monday"
    print("[PASS] Saturday -> Monday")


def test_sunday_to_monday():
    """Sunday should map to Monday."""
    sunday = dt.date(2026, 3, 1)  # Sunday, Mar 1, 2026
    assert sunday.weekday() == 6, "Test data error: should be Sunday"
    result = _next_trading_weekday(sunday)
    assert result == dt.date(2026, 3, 2), f"Expected Monday Mar 2, got {result}"
    assert result.weekday() == 0, "Result should be Monday"
    print("[PASS] Sunday -> Monday")


def test_monday_to_tuesday():
    """Monday should map to Tuesday."""
    monday = dt.date(2026, 3, 2)  # Monday, Mar 2, 2026
    assert monday.weekday() == 0, "Test data error: should be Monday"
    result = _next_trading_weekday(monday)
    assert result == dt.date(2026, 3, 3), f"Expected Tuesday Mar 3, got {result}"
    assert result.weekday() == 1, "Result should be Tuesday"
    print("[PASS] Monday -> Tuesday")


def test_tuesday_to_wednesday():
    """Tuesday should map to Wednesday."""
    tuesday = dt.date(2026, 3, 3)  # Tuesday, Mar 3, 2026
    assert tuesday.weekday() == 1, "Test data error: should be Tuesday"
    result = _next_trading_weekday(tuesday)
    assert result == dt.date(2026, 3, 4), f"Expected Wednesday Mar 4, got {result}"
    assert result.weekday() == 2, "Result should be Wednesday"
    print("[PASS] Tuesday -> Wednesday")


def test_wednesday_to_thursday():
    """Wednesday should map to Thursday."""
    wednesday = dt.date(2026, 3, 4)  # Wednesday, Mar 4, 2026
    assert wednesday.weekday() == 2, "Test data error: should be Wednesday"
    result = _next_trading_weekday(wednesday)
    assert result == dt.date(2026, 3, 5), f"Expected Thursday Mar 5, got {result}"
    assert result.weekday() == 3, "Result should be Thursday"
    print("[PASS] Wednesday -> Thursday")


def test_thursday_to_friday():
    """Thursday should map to Friday."""
    thursday = dt.date(2026, 3, 5)  # Thursday, Mar 5, 2026
    assert thursday.weekday() == 3, "Test data error: should be Thursday"
    result = _next_trading_weekday(thursday)
    assert result == dt.date(2026, 3, 6), f"Expected Friday Mar 6, got {result}"
    assert result.weekday() == 4, "Result should be Friday"
    print("[PASS] Thursday -> Friday")


if __name__ == "__main__":
    print("Testing _next_trading_weekday()...\n")
    test_friday_to_monday()
    test_saturday_to_monday()
    test_sunday_to_monday()
    test_monday_to_tuesday()
    test_tuesday_to_wednesday()
    test_wednesday_to_thursday()
    test_thursday_to_friday()
    print("\n[SUCCESS] All tests passed!")

