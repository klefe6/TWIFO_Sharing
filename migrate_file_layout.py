"""
Migration Script: Move existing TWIFO files to new layout
Purpose: Migrate PDFs and summaries from flat structure to organized artifacts/
Author: Kevin Lefebvre
Last Updated: 2026-02-12

This script:
1. Moves original PDFs from root FILES_DIR to originals/
2. Moves summary files (__sum.*) to artifacts/<basename>/
3. Creates a backup of the current state before migration
4. Provides dry-run mode to preview changes
"""

import sys
import shutil
from pathlib import Path
from typing import Dict, List
import argparse

try:
    from path_manager import TWIFOPathManager, get_path_manager
except ImportError:
    print("ERROR: path_manager.py not found. Make sure it's in the same directory.")
    sys.exit(1)


def create_backup(files_dir: Path) -> Path:
    """Create a timestamped backup directory."""
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = files_dir.parent / f"TWIFO_BACKUP_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def scan_legacy_files(files_dir: Path) -> Dict[str, List[Path]]:
    """
    Scan for files in root FILES_DIR that need migration.
    
    Returns:
        Dict with keys: 'originals', 'summaries', 'other'
    """
    results = {
        'originals': [],
        'summaries': [],
        'other': []
    }
    
    if not files_dir.exists():
        return results
    
    for item in files_dir.iterdir():
        if not item.is_file():
            continue
        
        filename = item.name
        
        # Original PDFs (not summaries)
        if filename.endswith('.pdf') and '__sum' not in filename and '__ocr' not in filename:
            results['originals'].append(item)
        
        # Summary files
        elif '__sum.' in filename:
            results['summaries'].append(item)
        
        # Other files (debug, OCR, etc.)
        else:
            results['other'].append(item)
    
    return results


def migrate_files(files_dir: Path, dry_run: bool = False, create_backup_dir: bool = True) -> Dict[str, int]:
    """
    Migrate files to new layout.
    
    Args:
        files_dir: Base directory (FILES_DIR)
        dry_run: If True, only print what would be done
        create_backup_dir: If True, create backup before migrating
    
    Returns:
        Dict with migration counts
    """
    pm = TWIFOPathManager(files_dir)
    
    # Scan for files to migrate
    files = scan_legacy_files(files_dir)
    
    print(f"\n{'='*60}")
    print("TWIFO File Migration - New Layout")
    print(f"{'='*60}")
    print(f"Files DIR: {files_dir}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"\nFound:")
    print(f"  - Original PDFs: {len(files['originals'])}")
    print(f"  - Summary files: {len(files['summaries'])}")
    print(f"  - Other files: {len(files['other'])}")
    print()
    
    if not files['originals'] and not files['summaries']:
        print("No files to migrate.")
        return {'originals': 0, 'artifacts': 0, 'skipped': 0}
    
    # Create backup if requested
    if create_backup_dir and not dry_run:
        backup_dir = create_backup(files_dir)
        print(f"Backup directory created: {backup_dir}")
        
        # Copy files to backup
        for file_list in files.values():
            for f in file_list:
                backup_path = backup_dir / f.name
                shutil.copy2(f, backup_path)
        
        print(f"Backed up {sum(len(v) for v in files.values())} files\n")
    
    # Migrate files
    counts = pm.migrate_all_legacy_files() if not dry_run else {'originals': 0, 'artifacts': 0, 'skipped': 0}
    
    if dry_run:
        print("DRY RUN - Would perform the following migrations:")
        print()
        
        # Originals
        print(f"Original PDFs → {pm.originals_dir}")
        for orig in files['originals'][:10]:  # Show first 10
            print(f"  {orig.name}")
        if len(files['originals']) > 10:
            print(f"  ... and {len(files['originals']) - 10} more")
        print()
        
        # Summaries (group by basename)
        summary_basenames = {}
        for summ in files['summaries']:
            basename = summ.name.split('__sum')[0]
            if basename not in summary_basenames:
                summary_basenames[basename] = []
            summary_basenames[basename].append(summ)
        
        print(f"Summary files → {pm.artifacts_dir}/<basename>/")
        for basename, summ_files in list(summary_basenames.items())[:5]:  # Show first 5
            print(f"  {basename}/")
            for sf in summ_files:
                artifact_name = sf.name.replace(f"{basename}__sum.", "sum.")
                if '__sum_debug_raw.txt' in sf.name:
                    artifact_name = 'extracted.txt'
                print(f"    - {artifact_name}")
        if len(summary_basenames) > 5:
            print(f"  ... and {len(summary_basenames) - 5} more artifact directories")
        print()
        
        counts = {
            'originals': len(files['originals']),
            'artifacts': len(files['summaries']),
            'skipped': len(files['other'])
        }
    else:
        print("Migration complete!")
        print(f"  - Moved {counts['originals']} original PDFs")
        print(f"  - Moved {counts['artifacts']} artifact files")
        print(f"  - Skipped {counts['skipped']} other files")
        print()
    
    return counts


def verify_migration(files_dir: Path):
    """Verify the migration was successful."""
    pm = TWIFOPathManager(files_dir)
    
    print(f"\n{'='*60}")
    print("Migration Verification")
    print(f"{'='*60}")
    
    # Check originals
    originals = pm.list_originals()
    print(f"✓ Originals directory: {len(originals)} PDFs")
    
    # Check artifacts
    artifacts = pm.list_artifacts_with_summaries()
    print(f"✓ Artifacts directory: {len(artifacts)} artifact sets")
    
    # Sample check
    if originals and artifacts:
        print("\nSample files:")
        for orig in originals[:3]:
            print(f"  Original: {orig}")
            basename = orig.replace('.pdf', '')
            has_pdf, has_json, has_txt = pm.has_summary(basename)
            status = []
            if has_pdf:
                status.append("sum.pdf")
            if has_json:
                status.append("sum.json")
            if has_txt:
                status.append("sum.txt")
            if status:
                print(f"    Artifacts: {', '.join(status)}")
            else:
                print(f"    Artifacts: (none)")
    
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Migrate TWIFO files to new layout (originals/ + artifacts/)"
    )
    parser.add_argument(
        '--files-dir',
        type=Path,
        default=Path(r'C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE'),
        help='Base directory (FILES_DIR)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without actually moving files'
    )
    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backup (not recommended)'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify existing migration, do not migrate'
    )
    
    args = parser.parse_args()
    
    if args.verify_only:
        verify_migration(args.files_dir)
        return
    
    # Confirm before proceeding (unless dry-run)
    if not args.dry_run:
        print(f"\nWARNING: This will reorganize files in: {args.files_dir}")
        if not args.no_backup:
            print("A backup will be created first.")
        else:
            print("NO BACKUP will be created (--no-backup flag).")
        
        response = input("\nProceed with migration? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Migration cancelled.")
            return
    
    # Migrate
    counts = migrate_files(
        args.files_dir,
        dry_run=args.dry_run,
        create_backup_dir=not args.no_backup
    )
    
    if not args.dry_run:
        verify_migration(args.files_dir)
    
    print("Done!")
    if args.dry_run:
        print("\nRun without --dry-run to perform actual migration.")


if __name__ == "__main__":
    main()
