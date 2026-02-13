"""
Critic pass documentation — structural cleanup rules (deterministic, no LLM).
Purpose: Document the rules applied by the post-generation critic pass (Step D.7).
Author: Kevin Lefebvre
Last Updated: 2026-02-12

The critic pass is a deterministic code step (not an LLM call). It enforces:

1. DEDUPLICATION
   - Remove semantically duplicated bullets across tldr, what_moved_today,
     what_can_move_tomorrow, what_occurred, and forward_watch.
   - Two bullets are "duplicated" if their normalized text (lowercase, stripped
     punctuation, collapsed whitespace) has Jaccard token overlap >= 0.70.
   - When a duplicate is found, keep the FIRST occurrence (by section priority:
     tldr > what_moved_today > what_can_move_tomorrow > what_occurred > forward_watch).
   - The critic NEVER adds new bullets — only removes duplicates.

2. EVIDENCE QUOTE VALIDATION
   - Every string in fingerprint_quotes[] must be a near-verbatim substring of
     the source text (fuzzy: lowercased, whitespace-collapsed).
   - Every trade_ideas[].source_quote must be a near-verbatim substring.
   - Quotes that fail validation are removed (not replaced).
   - If fingerprint_quotes drops below 3, flag _meta.critic_warnings.

3. NUMERIC CLAIMS COMPLETENESS
   - Walk the entire JSON for numeric tokens (reusing the D.5 verifier's walker).
   - Every number found outside numeric_claims[] must already exist inside it.
   - If a number is used but missing from numeric_claims[], and it IS present
     in the source text, auto-register it with value + context from the path.
   - If a number is used but missing from numeric_claims[] and NOT in source,
     remove it from the field (same as D.5 scrubbing).
   - The critic NEVER invents new numbers — only registers or removes existing ones.

4. INVARIANTS
   - Output must be valid JSON.
   - No new facts, entities, or claims are ever added.
   - Section keys are never added or removed.
   - _meta.critic_pass = True is stamped on the output.
   - _meta.critic_dedup_count records how many bullets were removed.
   - _meta.critic_quote_drops records how many quotes failed validation.
   - _meta.critic_numeric_registrations records auto-registered claims.
"""

CRITIC_PASS_VERSION = "1.0"
