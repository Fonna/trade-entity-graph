from trade_entity_graph.config import get_settings
from trade_entity_graph.utils.normalization import normalize_company_name


def test_settings_app_name() -> None:
    assert get_settings().app_name == "trade-entity-graph"


def test_normalize_company_name() -> None:
    assert normalize_company_name("  Acme   Trading ltd ") == "ACME TRADING LTD"
