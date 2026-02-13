"""
Tests for TWIFO Extraction Caching
Purpose: Verify extraction caching with SHA256 keys
Author: Kevin Lefebvre
Last Updated: 2026-02-12
"""

import tempfile
import shutil
from pathlib import Path
import json
import time
import pytest


def test_extraction_cache_hit():
    """Test that cached extraction is reused when PDF hasn't changed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from path_manager import TWIFOPathManager
        from summarize_pdf import extract_text, compute_pdf_sha256
        
        pm = TWIFOPathManager(Path(tmpdir))
        
        # Create a fake PDF (just a text file for testing)
        pdf_path = pm.original_pdf_path("test_doc.pdf")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake pdf content for testing")
        
        # Compute SHA256
        pdf_sha256 = compute_pdf_sha256(pdf_path)
        
        # Create fake cache files
        basename = "test_doc"
        extracted_txt = pm.artifact_path(basename, "extracted.txt")
        extraction_json = pm.artifact_path(basename, "extraction.json")
        
        pm.ensure_artifact_dir(basename)
        extracted_txt.write_text("This is cached extracted text")
        
        cache_data = {
            "pdf_sha256": pdf_sha256,
            "method_used": "pypdf",
            "status": "ok",
            "pages_total": 5,
            "pages_with_text": 5,
            "chars_total": 1000,
            "ocr_used": False,
            "errors": [],
            "created_at": "2026-02-12T10:00:00",
            "duration_ms": 100,
        }
        with open(extraction_json, 'w') as f:
            json.dump(cache_data, f)
        
        # Try extraction - should use cache
        from summarize_pdf import load_extraction_cache
        result = load_extraction_cache(pdf_path, pm)
        
        assert result is not None
        text, meta = result
        assert text == "This is cached extracted text"
        assert meta['method_used'] == 'pypdf'
        assert meta['chars_total'] == 1000


def test_extraction_cache_miss_on_pdf_change():
    """Test that cache is invalidated when PDF changes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from path_manager import TWIFOPathManager
        from summarize_pdf import compute_pdf_sha256, load_extraction_cache
        
        pm = TWIFOPathManager(Path(tmpdir))
        
        # Create original PDF
        pdf_path = pm.original_pdf_path("test_doc.pdf")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"original content")
        
        original_sha256 = compute_pdf_sha256(pdf_path)
        
        # Create cache with original SHA256
        basename = "test_doc"
        extracted_txt = pm.artifact_path(basename, "extracted.txt")
        extraction_json = pm.artifact_path(basename, "extraction.json")
        
        pm.ensure_artifact_dir(basename)
        extracted_txt.write_text("Cached text for original")
        
        cache_data = {
            "pdf_sha256": original_sha256,
            "method_used": "pypdf",
            "status": "ok",
            "pages_total": 1,
            "pages_with_text": 1,
            "chars_total": 100,
            "ocr_used": False,
            "errors": [],
            "created_at": "2026-02-12T10:00:00",
            "duration_ms": 50,
        }
        with open(extraction_json, 'w') as f:
            json.dump(cache_data, f)
        
        # Modify PDF content
        pdf_path.write_bytes(b"modified content - different!")
        
        # Try to load cache - should return None (cache invalid)
        result = load_extraction_cache(pdf_path, pm)
        assert result is None


def test_extraction_cache_miss_on_missing_files():
    """Test that cache miss occurs when cache files don't exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from path_manager import TWIFOPathManager
        from summarize_pdf import load_extraction_cache
        
        pm = TWIFOPathManager(Path(tmpdir))
        
        # Create PDF but no cache
        pdf_path = pm.original_pdf_path("test_doc.pdf")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"pdf content")
        
        # Try to load cache - should return None (no cache files)
        result = load_extraction_cache(pdf_path, pm)
        assert result is None


def test_save_extraction_cache():
    """Test that extraction cache is saved correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from path_manager import TWIFOPathManager
        from summarize_pdf import save_extraction_cache, compute_pdf_sha256
        
        pm = TWIFOPathManager(Path(tmpdir))
        
        # Create PDF
        pdf_path = pm.original_pdf_path("test_doc.pdf")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"pdf content for cache test")
        
        pdf_sha256 = compute_pdf_sha256(pdf_path)
        
        # Save extraction cache
        text = "Extracted text from PDF"
        extraction_meta = {
            "status": "ok",
            "method_used": "pypdf",
            "pages_total": 3,
            "pages_with_text": 3,
            "ocr_used": False,
            "errors": []
        }
        
        save_extraction_cache(pdf_path, text, extraction_meta, pdf_sha256, 150, pm)
        
        # Verify files were created
        basename = "test_doc"
        extracted_txt = pm.artifact_path(basename, "extracted.txt")
        extraction_json = pm.artifact_path(basename, "extraction.json")
        
        assert extracted_txt.exists()
        assert extraction_json.exists()
        
        # Verify content
        assert extracted_txt.read_text().strip() == text
        
        with open(extraction_json, 'r') as f:
            cache_data = json.load(f)
        
        assert cache_data['pdf_sha256'] == pdf_sha256
        assert cache_data['method_used'] == 'pypdf'
        assert cache_data['pages_total'] == 3
        assert cache_data['chars_total'] == len(text)
        assert cache_data['duration_ms'] == 150
        assert 'created_at' in cache_data


def test_extraction_metadata_structure():
    """Test that extraction metadata has all required fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from path_manager import TWIFOPathManager
        from summarize_pdf import save_extraction_cache, compute_pdf_sha256
        
        pm = TWIFOPathManager(Path(tmpdir))
        
        pdf_path = pm.original_pdf_path("test_doc.pdf")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"test content")
        
        pdf_sha256 = compute_pdf_sha256(pdf_path)
        
        text = "Sample extracted text"
        extraction_meta = {
            "status": "ok",
            "method_used": "pdfplumber",
            "pages_total": 5,
            "pages_with_text": 4,
            "ocr_used": False,
            "errors": ["warning: page 3 had issues"]
        }
        
        save_extraction_cache(pdf_path, text, extraction_meta, pdf_sha256, 250, pm)
        
        # Load and verify structure
        extraction_json = pm.artifact_path("test_doc", "extraction.json")
        with open(extraction_json, 'r') as f:
            data = json.load(f)
        
        # Required fields
        required_fields = [
            'pdf_sha256',
            'method_used',
            'status',
            'pages_total',
            'pages_with_text',
            'chars_total',
            'ocr_used',
            'errors',
            'created_at',
            'duration_ms'
        ]
        
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"


def test_ocr_metadata_tracking():
    """Test that OCR usage is properly tracked in metadata."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from path_manager import TWIFOPathManager
        from summarize_pdf import save_extraction_cache, compute_pdf_sha256
        
        pm = TWIFOPathManager(Path(tmpdir))
        
        pdf_path = pm.original_pdf_path("ocr_test.pdf")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"image-only pdf")
        
        pdf_sha256 = compute_pdf_sha256(pdf_path)
        
        # Simulate OCR extraction
        text = "Text extracted via OCR"
        extraction_meta = {
            "status": "ok",
            "method_used": "ocr_pymupdf+tesseract",
            "pages_total": 2,
            "pages_with_text": 2,
            "ocr_used": True,
            "errors": []
        }
        
        save_extraction_cache(pdf_path, text, extraction_meta, pdf_sha256, 5000, pm)
        
        # Verify OCR flag is preserved
        extraction_json = pm.artifact_path("ocr_test", "extraction.json")
        with open(extraction_json, 'r') as f:
            data = json.load(f)
        
        assert data['ocr_used'] is True
        assert data['method_used'] == "ocr_pymupdf+tesseract"
        assert data['duration_ms'] == 5000  # OCR is slow


def test_compute_pdf_sha256():
    """Test SHA256 computation for PDFs."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from summarize_pdf import compute_pdf_sha256
        
        pdf_path = Path(tmpdir) / "test.pdf"
        
        # Create PDF with known content
        content = b"Test PDF content for SHA256"
        pdf_path.write_bytes(content)
        
        # Compute hash
        sha256 = compute_pdf_sha256(pdf_path)
        
        # Verify it's a valid hex string
        assert len(sha256) == 64
        assert all(c in '0123456789abcdef' for c in sha256)
        
        # Verify it's deterministic
        sha256_2 = compute_pdf_sha256(pdf_path)
        assert sha256 == sha256_2
        
        # Verify it changes when content changes
        pdf_path.write_bytes(b"Different content")
        sha256_3 = compute_pdf_sha256(pdf_path)
        assert sha256 != sha256_3


def test_cache_performance_benefit():
    """Test that cache lookup is faster than re-extraction."""
    with tempfile.TemporaryDirectory() as tmpdir:
        from path_manager import TWIFOPathManager
        from summarize_pdf import save_extraction_cache, load_extraction_cache, compute_pdf_sha256
        
        pm = TWIFOPathManager(Path(tmpdir))
        
        pdf_path = pm.original_pdf_path("perf_test.pdf")
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"pdf content " * 1000)  # Larger file
        
        pdf_sha256 = compute_pdf_sha256(pdf_path)
        
        # Simulate slow extraction
        text = "Extracted text " * 100
        extraction_meta = {
            "status": "ok",
            "method_used": "pypdf",
            "pages_total": 10,
            "pages_with_text": 10,
            "ocr_used": False,
            "errors": []
        }
        
        # Save to cache
        save_extraction_cache(pdf_path, text, extraction_meta, pdf_sha256, 1000, pm)
        
        # Measure cache load time
        start = time.time()
        result = load_extraction_cache(pdf_path, pm)
        cache_time = time.time() - start
        
        assert result is not None
        assert cache_time < 0.1  # Should be very fast (< 100ms)


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v"])
