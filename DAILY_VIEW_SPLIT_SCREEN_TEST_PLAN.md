# Daily View Split-Screen Article View - Test Plan

## Overview

This test plan covers the new split-screen view for individual articles in Daily View. The split-screen shows the AI summary on the left (45%) and the original article on the right (55%).

## Scope

**Modified**: Daily View article detail rendering only
**NOT Modified**: Daily Summary rollup page (completely unchanged)

---

## Test 1: Basic Split-Screen Rendering

### Steps:
1. Start Twifo application
2. Navigate to Daily View tab
3. Select a date with articles
4. Click on an individual article (not the summary button)

### Expected:
- ✅ Split-screen layout appears
- ✅ Left pane shows AI summary (45% width)
- ✅ Right pane shows original article or fallback message (55% width)
- ✅ Both panes have independent scroll
- ✅ Vertical divider line between panes
- ✅ Layout is responsive (stacks on narrow screens)

### Pass Criteria:
- Split-screen renders without errors
- Both panes visible and scrollable
- No layout overflow or broken styling

---

## Test 2: Original PDF Found

### Steps:
1. Navigate to Daily View
2. Click an article that has an original PDF in its artifact folder
   - Look for folders with `original.pdf`, `source.pdf`, or any non-`sum.pdf` PDF

### Expected:
- ✅ Right pane shows "Original Article" header
- ✅ "↗ Open in New Tab" link present and functional
- ✅ PDF embedded in iframe
- ✅ PDF loads and displays correctly
- ✅ PDF scrolls independently from left pane

### Pass Criteria:
- Original PDF renders in iframe
- "Open in New Tab" link opens PDF in new browser tab
- No console errors

---

## Test 3: Original PDF Not Found

### Steps:
1. Navigate to Daily View
2. Click an article that does NOT have an original PDF
   - Artifact folder only contains `sum.json` and `sum.pdf`

### Expected:
- ✅ Right pane shows "Original Article" header
- ✅ Fallback message: "📄 Original article not available"
- ✅ Explanation text: "The original PDF was not found..."
- ✅ Yellow warning box styling
- ✅ No broken iframe or error

### Pass Criteria:
- Graceful fallback message displayed
- No console errors or broken elements
- User understands why original is not available

---

## Test 4: Summary-Only View (sum.pdf Strategy)

### Steps:
1. Navigate to Daily View
2. Click an article that only has `sum.pdf` (no `sum.json`)

### Expected:
- ✅ Split-screen layout still appears
- ✅ Left pane shows embedded `sum.pdf`
- ✅ Right pane attempts to find original PDF
- ✅ If no original found, shows fallback message

### Pass Criteria:
- Split-screen works even when summary is PDF-only
- No rendering errors

---

## Test 5: Error Handling

### Steps:
1. Navigate to Daily View
2. Click an article with corrupted or missing summary

### Expected:
- ✅ Split-screen layout still wraps error message
- ✅ Left pane shows error: "Error loading summary"
- ✅ Right pane shows original or fallback
- ✅ No application crash

### Pass Criteria:
- Errors handled gracefully
- Split-screen layout maintained
- User sees clear error message

---

## Test 6: Daily Summary NOT Affected

### Steps:
1. Navigate to Daily View
2. Click the "Summary for {date} & Prep for Today" button (top of sidebar)

### Expected:
- ✅ Daily Summary rollup page renders normally
- ✅ NO split-screen layout (full-width recap)
- ✅ All sections render correctly (TLDR, Volatility, Risk Flags, etc.)
- ✅ No changes to Daily Summary behavior

### Pass Criteria:
- Daily Summary completely unchanged
- No split-screen applied to rollup view
- All existing functionality works

---

## Test 7: Navigation Between Views

### Steps:
1. Navigate to Daily View
2. Click an individual article → Split-screen appears
3. Click another article → Split-screen updates
4. Click Daily Summary button → Full-width rollup appears
5. Click an article again → Split-screen reappears

### Expected:
- ✅ Smooth transitions between views
- ✅ No stale content from previous article
- ✅ Original PDF updates for each article
- ✅ No memory leaks or performance issues

### Pass Criteria:
- Navigation works smoothly
- Content updates correctly
- No console errors

---

## Test 8: Mobile/Responsive Behavior

### Steps:
1. Navigate to Daily View on mobile or narrow browser window (< 800px)
2. Click an individual article

### Expected:
- ✅ Panes stack vertically (flex-wrap)
- ✅ Summary pane on top
- ✅ Original pane below
- ✅ Both panes full-width
- ✅ No horizontal scroll

### Pass Criteria:
- Responsive layout works
- No broken styling on mobile
- Content readable and accessible

---

## Test 9: Open in New Tab

### Steps:
1. Navigate to Daily View
2. Click an article with original PDF
3. Click "↗ Open in New Tab" link in right pane

### Expected:
- ✅ Original PDF opens in new browser tab
- ✅ PDF loads directly (not embedded)
- ✅ Original tab remains on split-screen view

### Pass Criteria:
- Link opens PDF in new tab
- No navigation away from current view

---

## Test 10: Performance

### Steps:
1. Navigate to Daily View with 20+ articles
2. Rapidly click between different articles

### Expected:
- ✅ Split-screen renders quickly (< 1 second)
- ✅ No lag or freezing
- ✅ Smooth scrolling in both panes
- ✅ No memory buildup

### Pass Criteria:
- Performance acceptable
- No noticeable slowdown
- Browser remains responsive

---

## Regression Tests

### Test R1: Daily Summary Unchanged

**Verify**:
- Run existing Daily Summary tests
- Confirm `render_rollup_summary` function unchanged
- Confirm `_build_card` function unchanged
- Confirm all rollup callbacks unchanged

**Pass Criteria**:
- All existing tests pass
- No diffs in rollup-related functions

### Test R2: Article List Unchanged

**Verify**:
- Sidebar article list still renders correctly
- Clicking articles still triggers callback
- Article metadata (title, provider, frequency) displays correctly

**Pass Criteria**:
- No changes to sidebar behavior
- All article buttons functional

---

## Security Checks

### S1: File Path Validation

**Verify**:
- `_find_original_pdf` only searches within artifact folder
- No arbitrary file reads outside `artifacts/` directory
- Path traversal attacks prevented

### S2: Iframe Sandbox

**Note**: Current implementation uses basic iframe without sandbox attribute.

**Future Enhancement** (optional):
- Add `sandbox="allow-same-origin allow-scripts"` to iframe
- Add `referrerPolicy="no-referrer"` for privacy

---

## Known Limitations

1. **No toggle control**: Split-screen is always on for individual articles
   - Future enhancement: Add toggle button to collapse right pane
   
2. **PDF-only support**: Original article must be PDF
   - HTML/text rendering not implemented
   - Future enhancement: Support HTML rendering with sanitization

3. **No draggable divider**: Pane widths are fixed (45%/55%)
   - Future enhancement: Add resizable divider

4. **Original PDF detection**: Simple heuristic (looks for non-`sum.pdf` files)
   - May not work if artifact folder has multiple PDFs
   - Future enhancement: Store original filename in metadata

---

## Files Modified

1. **twifo.py**:
   - Added `_find_original_pdf()` helper
   - Added `_render_original_article_pane()` helper
   - Added `_build_split_screen_layout()` wrapper
   - Modified `display_daily_article_summary()` callback (3 return statements)

## Files NOT Modified

1. **twifo.py** (rollup functions):
   - `render_rollup_summary()` - unchanged
   - `render_rollup_sections_detail()` - unchanged
   - `_build_card()` - unchanged
   - All rollup-related helpers - unchanged

2. **rollups.py** - completely unchanged

3. **twifo_app.py** - completely unchanged

---

## Success Criteria

✅ All 10 functional tests pass
✅ Both regression tests pass
✅ Security checks pass
✅ No linter errors
✅ Daily Summary completely unchanged
✅ Performance acceptable

---

## Manual Test Execution

Date: _______________
Tester: _______________

| Test | Pass | Fail | Notes |
|------|------|------|-------|
| Test 1: Basic Split-Screen | ☐ | ☐ | |
| Test 2: Original PDF Found | ☐ | ☐ | |
| Test 3: Original PDF Not Found | ☐ | ☐ | |
| Test 4: Summary-Only View | ☐ | ☐ | |
| Test 5: Error Handling | ☐ | ☐ | |
| Test 6: Daily Summary NOT Affected | ☐ | ☐ | |
| Test 7: Navigation Between Views | ☐ | ☐ | |
| Test 8: Mobile/Responsive | ☐ | ☐ | |
| Test 9: Open in New Tab | ☐ | ☐ | |
| Test 10: Performance | ☐ | ☐ | |
| R1: Daily Summary Unchanged | ☐ | ☐ | |
| R2: Article List Unchanged | ☐ | ☐ | |

---

**Overall Result**: ☐ PASS ☐ FAIL

**Notes**:

