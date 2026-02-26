from pathlib import Path
import sys
from summarize_pdf import summarize_pdf
from path_manager import get_path_manager

ARTIFACTS_DIR = Path(r"C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE\artifacts")
TARGET_DATE = "20260211"

def main():
    pm = get_path_manager()
    folders = sorted([d for d in ARTIFACTS_DIR.iterdir() if d.is_dir() and d.name.startswith(f"{TARGET_DATE}__")])
    print(f"[INFO] Found {len(folders)} artifact folders for {TARGET_DATE}")

    for folder in folders:
        print(f"[PROCESS] {folder.name}")
        basename = folder.name
        try:
            original_pdf = pm.original_path(basename)
        except Exception:
            original_pdf = folder / (basename + ".pdf")

        if not original_pdf or not Path(original_pdf).exists():
            print(f"  [SKIP] Original PDF not found for {basename} (tried {original_pdf})")
            continue

        try:
            summarize_pdf(Path(original_pdf), allow_ocr=False, path_manager=pm)
            print(f"  [OK] Regenerated sum.json for {basename}")
        except Exception as e:
            print(f"  [ERROR] Failed to summarize {basename}: {e}")

if __name__ == "__main__":
    main()

