"""Bridge module: re-exports csv_router from scripts/csv_exports for Vercel/FastAPI."""
import sys
from pathlib import Path

# Add project root to sys.path so we can import from scripts/
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from scripts.csv_exports import csv_router  # noqa: F401, E402
