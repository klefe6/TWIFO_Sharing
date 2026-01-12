# Option B Implementation Plan

This is a comprehensive plan for implementing Option B (Scan + Deep Dive) summaries with all required features.

## Status: Starting Implementation

Given the complexity, I'm implementing this systematically:

1. **Phase 1: Core Schema & Prompt Updates** (summarize_pdf.py)
   - Add helper functions for firm detection, date extraction, quality calculation
   - Update _call_openai_api() with Option B prompt
   - Update summarize_pdf() to build new schema structure
   
2. **Phase 2: PDF Rendering** (summary_render.py)
   - Update render_summary_pdf() to handle new Option B schema
   - Render Scan section first, then Deep Dive
   
3. **Phase 3: On-Demand PDF Generation** (twifo.py)
   - Add ensure_summary_pdf() function
   - Update /view route to generate PDFs on-demand
   
4. **Phase 4: Score Reading Updates** (twifo.py)
   - Update load_summary_score() to read from new schema location
   
5. **Phase 5: Daily/Weekly Rollups** (new scripts)
   - Create generate_daily_rollup.py
   - Create generate_weekly_rollup.py
   - Update twifo.py to show rollups

Let me start with Phase 1 now...

