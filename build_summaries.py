"""
Build Summary PDFs from JSON files

This script scans for __sum.json files and generates corresponding __sum.pdf files.
Can build one specific file or scan all directories.
"""

import os
import sys
from pathlib import Path

# Import the PDF renderer
try:
    from summary_render import render_summary_pdf
except ImportError:
    print("ERROR: summary_render module not found. Make sure reportlab is installed.")
    print("Install with: pip install reportlab")
    sys.exit(1)

# Directories to scan
FILES_DIR = Path(r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE")
SC_DIR = Path(r"C:\Users\H&CDanHughes\Documents\SC_files")


def build_one(json_path: Path) -> bool:
    """
    Build PDF for a single JSON file.
    Returns True if successful, False otherwise.
    """
    if not json_path.exists():
        print(f"[ERROR] JSON file not found: {json_path}")
        return False
    
    if not json_path.name.endswith("__sum.json"):
        print(f"[ERROR] Not a summary JSON file (must end with __sum.json): {json_path.name}")
        return False
    
    try:
        pdf_path = render_summary_pdf(json_path)
        print(f"[OK] Generated: {pdf_path}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to generate PDF for {json_path.name}: {e}")
        return False


def build_all():
    """
    Scan FILES_DIR and SC_DIR for __sum.json files and build missing PDFs.
    """
    dirs_to_scan = [FILES_DIR]
    if SC_DIR.exists():
        dirs_to_scan.append(SC_DIR)
    
    json_files = []
    for directory in dirs_to_scan:
        if not directory.exists():
            print(f"[WARN] Directory not found: {directory}")
            continue
        
        print(f"[INFO] Scanning: {directory}")
        for json_file in directory.glob("*__sum.json"):
            json_files.append(json_file)
    
    if not json_files:
        print("[INFO] No __sum.json files found.")
        return
    
    print(f"[INFO] Found {len(json_files)} summary JSON files.")
    
    built = 0
    skipped = 0
    failed = 0
    
    for json_path in json_files:
        pdf_path = json_path.with_suffix('.pdf')
        
        # Check if PDF exists and is newer than JSON
        if pdf_path.exists():
            json_mtime = json_path.stat().st_mtime
            pdf_mtime = pdf_path.stat().st_mtime
            
            if pdf_mtime >= json_mtime:
                skipped += 1
                print(f"[SKIP] PDF up to date: {pdf_path.name}")
                continue
        
        # Build PDF
        print(f"[BUILD] {json_path.name}...")
        if build_one(json_path):
            built += 1
        else:
            failed += 1
    
    print(f"\n[DONE] Built: {built}, Skipped: {skipped}, Failed: {failed}")


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  Build one:  python build_summaries.py <path_to_sum.json>")
        print("  Build all:  python build_summaries.py --all")
        sys.exit(1)
    
    arg = sys.argv[1]
    
    if arg == "--all":
        build_all()
    else:
        json_path = Path(arg)
        success = build_one(json_path)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
