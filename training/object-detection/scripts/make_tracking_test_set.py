#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

# Allows direct execution from repo root without requiring editable install.
REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from object_detection.tracking_eval.test_set import main


if __name__ == "__main__":
    main()
