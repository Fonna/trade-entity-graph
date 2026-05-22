"""Initialize the local SQLite database."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trade_entity_graph.db.connection import initialize_database

if __name__ == "__main__":
    db_path = initialize_database()
    print(f"Initialized database: {db_path}")
