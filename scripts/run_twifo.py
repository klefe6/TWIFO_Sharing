"""Load HCRESEARCH_API_KEY from a protected file and run twifo.py."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_api_key() -> str:
    key_file = os.environ.get("HCRESEARCH_API_KEY_FILE", "").strip()
    if not key_file:
        key_file = str(Path.home() / ".secrets" / "hcr_api_key_current.txt")
    path = Path(key_file)
    if not path.is_file():
        print(f"ERROR: HCR API key file not found: {path}", file=sys.stderr)
        raise SystemExit(1)
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        print(f"ERROR: HCR API key file is empty: {path}", file=sys.stderr)
        raise SystemExit(1)
    return key


def main() -> int:
    os.environ["HCRESEARCH_API_KEY"] = _load_api_key()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    twifo = ROOT / "twifo.py"
    if not twifo.is_file():
        print(f"ERROR: twifo.py not found at {twifo}", file=sys.stderr)
        return 1
    with open(twifo, encoding="utf-8") as handle:
        code = compile(handle.read(), str(twifo), "exec")
    globals_dict = {"__name__": "__main__", "__file__": str(twifo)}
    exec(code, globals_dict)  # noqa: S102
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
