"""Inspect a workbook before the M2 import pipeline is implemented."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trade_entity_graph.importers.excel_importer import inspect_workbook


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect an Excel/CSV workbook for import readiness."
    )
    parser.add_argument("path", help="Path to the source workbook")
    args = parser.parse_args()
    print(inspect_workbook(args.path))


if __name__ == "__main__":
    main()
