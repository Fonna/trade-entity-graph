"""Run the Streamlit MVP shell."""

from __future__ import annotations

import subprocess
import sys


if __name__ == "__main__":
    raise SystemExit(
        subprocess.call(
            [sys.executable, "-m", "streamlit", "run", "src/trade_entity_graph/ui/streamlit_app.py"]
        )
    )
