"""Order evidence loading for imports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

from trade_entity_graph.importers.field_mapping import get_value
from trade_entity_graph.importers.models import ImportErrorRecord, ImportSourceRow
from trade_entity_graph.utils.ids import new_id


@dataclass
class EvidenceLoadResult:
    evidence_count: int = 0
    success_rows: int = 0
    skipped_rows: list[str] = field(default_factory=list)
    import_errors: list[ImportErrorRecord] = field(default_factory=list)


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def load_order_evidence(
    connection: sqlite3.Connection,
    rows: list[ImportSourceRow],
    *,
    run_id: str,
) -> EvidenceLoadResult:
    """Load source order rows into `order_evidence`."""

    result = EvidenceLoadResult()
    for row in rows:
        order_id = get_value(row.values, "order_id")
        if not order_id:
            result.skipped_rows.append(f"{row.source_file}:{row.source_row}: missing order_id")
            result.import_errors.append(
                ImportErrorRecord(
                    run_id=run_id,
                    error_type="missing_required_value",
                    severity="blocking",
                    message="订单号不能为空",
                    file_role="orders",
                    source_path=row.source_file,
                    sheet_name=row.source_sheet,
                    row_number=row.source_row,
                    normalized_field="order_id",
                    raw_value=order_id,
                )
            )
            continue

        raw_teu = get_value(row.values, "teu")
        try:
            teu = _to_float(raw_teu)
        except (TypeError, ValueError):
            result.skipped_rows.append(f"{row.source_file}:{row.source_row}: invalid teu")
            result.import_errors.append(
                ImportErrorRecord(
                    run_id=run_id,
                    error_type="invalid_numeric_value",
                    severity="blocking",
                    message="TEU 必须是数字",
                    file_role="orders",
                    source_path=row.source_file,
                    sheet_name=row.source_sheet,
                    row_number=row.source_row,
                    normalized_field="teu",
                    raw_value=raw_teu,
                )
            )
            continue

        connection.execute(
            """
            INSERT INTO order_evidence (
                evidence_id, order_id, teu, product_name, function_category,
                destination_country, destination_port, order_date, customer_name,
                shipper_name, consignee_name, notify_name, source_file, source_sheet,
                source_row, run_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_id("EVD"),
                str(order_id),
                teu,
                get_value(row.values, "product_name"),
                get_value(row.values, "function_category"),
                get_value(row.values, "destination_country"),
                get_value(row.values, "destination_port"),
                get_value(row.values, "order_date"),
                get_value(row.values, "customer_name"),
                get_value(row.values, "shipper_name"),
                get_value(row.values, "consignee_name"),
                get_value(row.values, "notify_name"),
                row.source_file,
                row.source_sheet,
                row.source_row,
                run_id,
            ),
        )
        result.evidence_count += 1
        result.success_rows += 1

    connection.commit()
    return result
