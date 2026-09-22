"""Shared paths for the Vintage project.

Every script reads real data (data/, marts_out/, models_out/) through VINTAGE_DATA_ROOT rather
than a relative path, so a secondary checkout of this repo can read the main checkout's data
without copying it.
"""

import os
from pathlib import Path

# Root that holds data/, marts_out/ and models_out/. Defaults to this repo (the main checkout);
# override with the VINTAGE_DATA_ROOT env var from a secondary checkout so it still points at the
# main checkout's data instead of the secondary checkout's own (empty) copy.
VINTAGE_DATA_ROOT = Path(os.environ.get("VINTAGE_DATA_ROOT", Path(__file__).resolve().parent))
