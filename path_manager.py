"""
TWIFO Path Manager - Centralized file layout and path resolution
Purpose: Enforce strict separation between originals and artifacts
Author: Kevin Lefebvre
Last Updated: 2026-02-12

Directory Structure:
  FILES_DIR/
    originals/           # Original PDFs (read-only, never overwrite)
      BOA_Report_20260212_w.pdf
    artifacts/           # Generated files (organized by basename)
      BOA_Report_20260212_w/
        extracted.txt    # Raw extracted text
        extraction.json  # Extraction metadata
        sum.json         # Summary JSON (twifo.sum.v1)
        sum.txt          # Summary text
        sum.pdf          # Rendered summary PDF
"""

from pathlib import Path
from typing import Optional, Tuple, Dict, List
import hashlib
import os


class TWIFOPathManager:
    """
    Centralized path management for TWIFO files.
    Enforces separation between originals and artifacts.
    """
    
    def __init__(self, files_dir: Path):
        """
        Initialize path manager with base directory.
        
        Args:
            files_dir: Base directory (e.g., FILES_DIR)
        """
        self.files_dir = Path(files_dir)
        self.originals_dir = self.files_dir / "originals"
        self.artifacts_dir = self.files_dir / "artifacts"
        
        # Ensure directories exist
        self.originals_dir.mkdir(parents=True, exist_ok=True)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
    
    def original_pdf_path(self, basename: str) -> Path:
        """Get path to original PDF in originals/ directory."""
        if not basename.endswith('.pdf'):
            basename = f"{basename}.pdf"
        return self.originals_dir / basename
    
    def artifact_dir(self, basename: str) -> Path:
        """
        Get artifact directory for a given PDF basename.
        Strips .pdf extension for directory name.
        """
        if basename.endswith('.pdf'):
            basename = basename[:-4]
        return self.artifacts_dir / basename
    
    def artifact_path(self, basename: str, artifact_type: str) -> Path:
        """
        Get path to a specific artifact.
        
        Args:
            basename: PDF basename (with or without .pdf)
            artifact_type: One of: 'extracted.txt', 'extraction.json', 
                          'sum.json', 'sum.txt', 'sum.pdf'
        
        Returns:
            Path to artifact file
        """
        return self.artifact_dir(basename) / artifact_type
    
    def ensure_artifact_dir(self, basename: str) -> Path:
        """Create artifact directory if it doesn't exist and return path."""
        art_dir = self.artifact_dir(basename)
        art_dir.mkdir(parents=True, exist_ok=True)
        return art_dir
    
    def has_original(self, basename: str) -> bool:
        """Check if original PDF exists."""
        return self.original_pdf_path(basename).exists()
    
    def has_summary(self, basename: str) -> Tuple[bool, bool, bool]:
        """
        Check which summary artifacts exist.
        
        Returns:
            Tuple of (has_sum_pdf, has_sum_json, has_sum_txt)
        """
        has_pdf = self.artifact_path(basename, 'sum.pdf').exists()
        has_json = self.artifact_path(basename, 'sum.json').exists()
        has_txt = self.artifact_path(basename, 'sum.txt').exists()
        return (has_pdf, has_json, has_txt)
    
    def compute_pdf_sha256(self, pdf_path: Path) -> str:
        """Compute SHA256 hash of PDF file."""
        sha256 = hashlib.sha256()
        with open(pdf_path, 'rb') as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()
    
    def list_originals(self) -> List[str]:
        """
        List all original PDF basenames (filenames without directory).
        Returns sorted list of PDF filenames.
        """
        if not self.originals_dir.exists():
            return []
        return sorted([
            f.name for f in self.originals_dir.glob("*.pdf")
            if f.is_file()
        ])
    
    def list_artifacts_with_summaries(self) -> List[Dict[str, any]]:
        """
        List all artifacts with summary files.
        
        Returns:
            List of dicts with keys: basename, has_sum_pdf, has_sum_json, 
            has_sum_txt, has_original
        """
        if not self.artifacts_dir.exists():
            return []
        
        results = []
        for art_dir in self.artifacts_dir.iterdir():
            if not art_dir.is_dir():
                continue
            
            basename = art_dir.name
            has_pdf, has_json, has_txt = self.has_summary(basename)
            has_orig = self.has_original(basename)
            
            # Only include if it has at least one summary artifact
            if has_pdf or has_json or has_txt:
                results.append({
                    'basename': basename,
                    'has_sum_pdf': has_pdf,
                    'has_sum_json': has_json,
                    'has_sum_txt': has_txt,
                    'has_original': has_orig,
                    'artifact_dir': str(art_dir)
                })
        
        return sorted(results, key=lambda x: x['basename'])
    
    def get_summary_paths(self, basename: str) -> Dict[str, Optional[Path]]:
        """
        Get all summary-related paths for a basename.
        
        Returns:
            Dict with keys: original_pdf, sum_json, sum_txt, sum_pdf
            Values are Path objects or None if file doesn't exist
        """
        orig = self.original_pdf_path(basename)
        sum_json = self.artifact_path(basename, 'sum.json')
        sum_txt = self.artifact_path(basename, 'sum.txt')
        sum_pdf = self.artifact_path(basename, 'sum.pdf')
        
        return {
            'original_pdf': orig if orig.exists() else None,
            'sum_json': sum_json if sum_json.exists() else None,
            'sum_txt': sum_txt if sum_txt.exists() else None,
            'sum_pdf': sum_pdf if sum_pdf.exists() else None,
        }
    
    def migrate_legacy_file(self, legacy_path: Path) -> Optional[Path]:
        """
        Migrate a legacy file from root FILES_DIR to new structure.
        
        - PDFs go to originals/
        - __sum.* files create artifact directories
        
        Returns:
            New path if migrated, None if skipped
        """
        if not legacy_path.exists():
            return None
        
        filename = legacy_path.name
        
        # Original PDF - move to originals/
        if filename.endswith('.pdf') and '__sum' not in filename:
            new_path = self.original_pdf_path(filename)
            if not new_path.exists():
                legacy_path.rename(new_path)
                return new_path
            return None
        
        # Summary files - move to artifacts/
        if '__sum.' in filename:
            # Extract basename (everything before __sum)
            basename = filename.split('__sum')[0]
            
            # Determine artifact type
            if filename.endswith('__sum.json'):
                artifact_type = 'sum.json'
            elif filename.endswith('__sum.txt'):
                artifact_type = 'sum.txt'
            elif filename.endswith('__sum.pdf'):
                artifact_type = 'sum.pdf'
            elif filename.endswith('__sum_debug_raw.txt'):
                artifact_type = 'extracted.txt'  # Rename debug file
            else:
                return None  # Unknown artifact type
            
            # Create artifact directory and move file
            art_dir = self.ensure_artifact_dir(basename)
            new_path = art_dir / artifact_type
            if not new_path.exists():
                legacy_path.rename(new_path)
                return new_path
            return None
        
        return None
    
    def migrate_all_legacy_files(self) -> Dict[str, int]:
        """
        Migrate all legacy files in FILES_DIR root to new structure.
        
        Returns:
            Dict with counts: {originals: N, artifacts: M, skipped: K}
        """
        counts = {'originals': 0, 'artifacts': 0, 'skipped': 0}
        
        if not self.files_dir.exists():
            return counts
        
        # Only migrate files in root FILES_DIR (not in subdirectories)
        for item in self.files_dir.iterdir():
            if not item.is_file():
                continue
            
            # Skip if already in new structure
            if item.parent == self.originals_dir or item.parent == self.artifacts_dir:
                continue
            
            new_path = self.migrate_legacy_file(item)
            if new_path:
                if new_path.parent == self.originals_dir:
                    counts['originals'] += 1
                else:
                    counts['artifacts'] += 1
            else:
                counts['skipped'] += 1
        
        return counts


# Singleton instance for convenience
_default_path_manager: Optional[TWIFOPathManager] = None


def get_path_manager(files_dir: Optional[Path] = None) -> TWIFOPathManager:
    """
    Get or create default path manager instance.
    
    Args:
        files_dir: Base directory (uses default if None)
    
    Returns:
        TWIFOPathManager instance
    """
    global _default_path_manager
    
    if files_dir is None:
        # Use default FILES_DIR from environment or hardcoded path
        files_dir = Path(os.getenv(
            'TWIFO_FILES_DIR',
            r'C:\Users\H&CDanHughes\Hughes & Company\Hughes & Company - Documents\8_Research\FOLDERS_AVAILABLE_ONLINE'
        ))
    
    if _default_path_manager is None or _default_path_manager.files_dir != files_dir:
        _default_path_manager = TWIFOPathManager(files_dir)
    
    return _default_path_manager


# Convenience functions for backward compatibility
def original_pdf_path(basename: str, files_dir: Optional[Path] = None) -> Path:
    """Get path to original PDF."""
    return get_path_manager(files_dir).original_pdf_path(basename)


def artifact_path(basename: str, artifact_type: str, files_dir: Optional[Path] = None) -> Path:
    """Get path to specific artifact."""
    return get_path_manager(files_dir).artifact_path(basename, artifact_type)


def has_summary(basename: str, files_dir: Optional[Path] = None) -> Tuple[bool, bool, bool]:
    """Check which summary artifacts exist."""
    return get_path_manager(files_dir).has_summary(basename)
