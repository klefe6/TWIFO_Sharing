"""
End-to-end integration test: path_manager enabled → summarize → render → confirm PDF exists.
Purpose: Prove the full pipeline produces a rendered PDF in the correct artifacts location.
Author: Kevin Lefebvre
Last Updated: 2026-02-12

Run this test:
    python test_e2e_path_manager.py
    # or with pytest:
    python -m pytest test_e2e_path_manager.py -v
"""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from path_manager import TWIFOPathManager
from summarize_pdf import summarize_pdf
from summary_render import render_summary_pdf


def create_minimal_pdf(pdf_path: Path) -> None:
    """Create a minimal valid PDF file (no external dependencies)."""
    # Minimal PDF structure that is technically valid
    pdf_content = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT /F1 12 Tf 100 700 Td (Test PDF) Tj ET
endstream
endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000206 00000 n 
trailer
<< /Size 5 /Root 1 0 R >>
startxref
300
%%EOF
"""
    pdf_path.write_bytes(pdf_content)


def get_mock_summary() -> dict:
    """Return a minimal valid summary dict that passes quality gate checks."""
    return {
        "schema_version": "twifo.sum.v1",
        "meta": {
            "provider": "TEST",
            "published_date": "20260212",
            "horizon": "d",
            "theme": "Market Analysis",
            "products": ["ES", "NQ"],
            "model": "gpt-4o-mini",
            "generated_at_iso": "2026-02-12T10:00:00",
        },
        "summary_score_0_10": 7,
        "sections": {
            "tldr": [
                {"text": "Fed minutes showed hawkish sentiment among FOMC members."},
                {"text": "ES futures declined 0.5% to 5,450 on rate concerns."},
                {"text": "Gold rallied to 2,050 as safe-haven demand increased."},
            ],
            "what_moved_today": [
                {
                    "product": "ES",
                    "direction": "bearish",
                    "level": "5,450",
                    "driver": "Fed minutes hawkish tone",
                    "text": "ES: bearish to 5,450 – Fed minutes hawkish tone",
                },
                {
                    "product": "GC",
                    "direction": "bullish",
                    "level": "2,050",
                    "driver": "Safe-haven flows",
                    "text": "GC: bullish to 2,050 – Safe-haven flows",
                },
            ],
            "what_can_move_tomorrow": [
                {
                    "product": "ES",
                    "direction": "neutral",
                    "level": "5,400-5,500",
                    "trigger": "CPI release",
                    "text": "ES: neutral at 5,400-5,500 – CPI release",
                },
            ],
        },
        "extraction": {
            "status": "ok",
            "method_used": "pypdf",
            "pages_total": 1,
            "pages_with_text": 1,
            "chars_total": 2500,
            "ocr_used": False,
            "errors": [],
        },
    }


def get_mock_extraction() -> tuple:
    """Return mock extraction result (text, metadata)."""
    text = (
        "Federal Reserve FOMC Meeting Minutes\n\n"
        "The Federal Reserve released its meeting minutes today, showing hawkish sentiment "
        "among committee members. Several participants noted that inflation remains elevated "
        "and suggested that additional rate hikes may be necessary. The minutes indicated that "
        "the committee discussed keeping rates higher for longer than previously anticipated.\n\n"
        "Market Reaction:\n"
        "ES futures declined 0.5% to 5,450 following the release. Treasury yields climbed with "
        "the 10-year reaching 4.25%. Gold rallied to 2,050 as investors sought safe-haven assets.\n\n"
        "Key Takeaways:\n"
        "1. Hawkish tone suggests potential for more rate hikes\n"
        "2. Inflation concerns remain central to policy decisions\n"
        "3. Labor market strength cited as supporting tight policy\n"
    ) * 3  # Repeat to ensure > MIN_TEXT_CHARS (1500)
    
    extraction_meta = {
        "status": "ok",
        "method_used": "pypdf",
        "pages_total": 1,
        "pages_with_text": 1,
        "chars_total": len(text),
        "ocr_used": False,
        "errors": [],
    }
    return text, extraction_meta


def test_e2e_path_manager_summarize_render():
    """
    End-to-end test: path_manager mode → summarize → render → PDF exists.
    
    This test:
    1. Sets up isolated tmp_path with path_manager
    2. Creates a minimal PDF in originals/
    3. Mocks LLM call to return valid summary (deterministic, no API call)
    4. Calls summarize_pdf with path_manager
    5. Calls render_summary_pdf with returned JSON path
    6. Asserts PDF exists and has size > 0
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        files_dir = Path(tmpdir)
        
        # Initialize path manager
        pm = TWIFOPathManager(files_dir)
        
        # Create minimal test PDF in originals/
        test_pdf_name = "TestReport_20260212_d.pdf"
        pdf_path = pm.original_pdf_path(test_pdf_name)
        create_minimal_pdf(pdf_path)
        assert pdf_path.exists(), "Test PDF should be created"
        
        # Mock extraction to avoid actual PDF parsing
        mock_text, mock_extraction = get_mock_extraction()
        
        # Mock LLM summarization to return valid summary (no API call)
        mock_summary = get_mock_summary()
        
        with patch("summarize_pdf.extract_text") as mock_extract, \
             patch("summarize_pdf._summarize_with_quality_retry") as mock_summarize:
            
            mock_extract.return_value = (mock_text, mock_extraction)
            mock_summarize.return_value = mock_summary
            
            # Call summarize_pdf with path_manager enabled
            sum_json, sum_json_path = summarize_pdf(
                pdf_path,
                model="gpt-4o-mini",
                allow_ocr=False,
                path_manager=pm,
                enable_triage=False,  # Skip triage for determinism
            )
        
        # Verify JSON was written to expected location
        expected_json_path = pm.artifact_path(test_pdf_name, "sum.json")
        assert sum_json_path == expected_json_path, (
            f"JSON path mismatch: got {sum_json_path}, expected {expected_json_path}"
        )
        assert sum_json_path.exists(), f"sum.json should exist at {sum_json_path}"
        assert sum_json_path.stat().st_size > 0, "sum.json should not be empty"
        
        # Verify sum_json is valid (not a stub)
        assert sum_json.get("schema_version") == "twifo.sum.v1"
        assert sum_json.get("sections", {}).get("tldr"), "Summary should have tldr section"
        
        # Now render the PDF using the returned path
        expected_pdf_path = pm.artifact_path(test_pdf_name, "sum.pdf")
        render_result = render_summary_pdf(sum_json_path, expected_pdf_path)
        
        # Assert render succeeded and PDF exists
        assert render_result is True, "render_summary_pdf should return True"
        assert expected_pdf_path.exists(), f"Rendered PDF should exist at {expected_pdf_path}"
        assert expected_pdf_path.stat().st_size > 0, "Rendered PDF should not be empty"
        
        # Verify PDF is actually a PDF (magic bytes)
        with open(expected_pdf_path, "rb") as f:
            magic = f.read(5)
        assert magic == b"%PDF-", "Rendered file should be a valid PDF"
        
        print(f"[OK] E2E test passed:")
        print(f"     JSON: {sum_json_path} ({sum_json_path.stat().st_size} bytes)")
        print(f"     PDF:  {expected_pdf_path} ({expected_pdf_path.stat().st_size} bytes)")


def test_e2e_path_manager_directory_structure():
    """
    Verify the path_manager creates correct directory structure.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        files_dir = Path(tmpdir)
        pm = TWIFOPathManager(files_dir)
        
        # Verify directories created
        assert (files_dir / "originals").exists()
        assert (files_dir / "artifacts").exists()
        
        # Create test PDF
        test_pdf_name = "Sample_20260212_w.pdf"
        pdf_path = pm.original_pdf_path(test_pdf_name)
        create_minimal_pdf(pdf_path)
        
        mock_text, mock_extraction = get_mock_extraction()
        mock_summary = get_mock_summary()
        
        with patch("summarize_pdf.extract_text") as mock_extract, \
             patch("summarize_pdf._summarize_with_quality_retry") as mock_summarize:
            
            mock_extract.return_value = (mock_text, mock_extraction)
            mock_summarize.return_value = mock_summary
            
            sum_json, sum_json_path = summarize_pdf(
                pdf_path,
                model="gpt-4o-mini",
                allow_ocr=False,
                path_manager=pm,
                enable_triage=False,
            )
        
        # Verify artifact directory structure
        basename = test_pdf_name.replace(".pdf", "")
        artifact_dir = files_dir / "artifacts" / basename
        assert artifact_dir.exists(), f"Artifact dir should exist: {artifact_dir}"
        assert (artifact_dir / "sum.json").exists(), "sum.json should exist in artifact dir"
        assert (artifact_dir / "sum.txt").exists(), "sum.txt should exist in artifact dir"
        
        print(f"[OK] Directory structure verified:")
        print(f"     originals/: {list((files_dir / 'originals').iterdir())}")
        print(f"     artifacts/{basename}/: {list(artifact_dir.iterdir())}")


if __name__ == "__main__":
    print("=" * 70)
    print("End-to-End Path Manager Integration Tests")
    print("=" * 70)
    
    import sys
    
    print("\n[1] test_e2e_path_manager_summarize_render")
    print("-" * 50)
    try:
        test_e2e_path_manager_summarize_render()
        print("[PASS] test_e2e_path_manager_summarize_render\n")
    except Exception as e:
        print(f"[FAIL] test_e2e_path_manager_summarize_render: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("\n[2] test_e2e_path_manager_directory_structure")
    print("-" * 50)
    try:
        test_e2e_path_manager_directory_structure()
        print("[PASS] test_e2e_path_manager_directory_structure\n")
    except Exception as e:
        print(f"[FAIL] test_e2e_path_manager_directory_structure: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("=" * 70)
    print("[OK] All E2E path_manager tests passed!")
    print("=" * 70)
