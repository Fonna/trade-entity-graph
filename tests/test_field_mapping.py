from trade_entity_graph.importers.field_mapping import resolve_rows_for_role
from trade_entity_graph.importers.models import ImportSourceRow


def test_resolve_rows_for_role_maps_real_order_column_variants() -> None:
    rows = [
        ImportSourceRow(
            source_file="orders.csv",
            source_sheet="orders",
            source_row=2,
            values={
                "业务编号": "SO-1",
                "Booking Customer": "Acme Trading Ltd",
                "Shipper": "Beta Factory Inc",
                "Consignee": "Omega Buyer LLC",
                "Notify Party": "Omega Buyer LLC",
                "箱量": "3.5",
                "目的国家": "MX",
                "品名": "Widget",
            },
        )
    ]

    resolved_rows, errors = resolve_rows_for_role(rows, role="orders", run_id="RUN_MAP")

    assert errors == []
    assert resolved_rows[0].values["order_id"] == "SO-1"
    assert resolved_rows[0].values["customer_name"] == "Acme Trading Ltd"
    assert resolved_rows[0].values["teu"] == "3.5"
    assert resolved_rows[0].values["product_name"] == "Widget"


def test_resolve_rows_for_role_records_missing_required_header() -> None:
    rows = [
        ImportSourceRow(
            source_file="orders.csv",
            source_sheet="orders",
            source_row=2,
            values={"客户名称": "Acme Trading Ltd"},
        )
    ]

    resolved_rows, errors = resolve_rows_for_role(rows, role="orders", run_id="RUN_MAP")

    assert resolved_rows == []
    assert errors[0].error_type == "missing_required_field"
    assert errors[0].severity == "blocking"
    assert errors[0].normalized_field == "order_id"


def test_resolve_rows_for_role_records_duplicate_mapping_warning() -> None:
    rows = [
        ImportSourceRow(
            source_file="entities.csv",
            source_sheet="entities",
            source_row=2,
            values={"标准名": "ACME TRADING", "企业标准名": "ACME TRADING DUP"},
        )
    ]

    resolved_rows, errors = resolve_rows_for_role(rows, role="entities", run_id="RUN_MAP")

    assert resolved_rows[0].values["canonical_name"] == "ACME TRADING"
    assert errors[0].error_type == "field_mapping_error"
    assert errors[0].severity == "warning"
