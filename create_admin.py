"""Compatibility wrapper; prefer python -m app.cli from backend."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))
from app.cli import main  # noqa: E402

if __name__ == "__main__":
    main()
