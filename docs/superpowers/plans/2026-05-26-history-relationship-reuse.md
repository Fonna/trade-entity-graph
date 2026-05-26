# History Relationship Reuse Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist historical relationship reuse results on new candidates, surface conflicts for manual review, and support human-approved superseding of incorrect historical conclusions.

**Architecture:** Add a focused history reuse service that classifies `relationship_claim` rows against current effective `curated_relationship` rows. Keep review mutations in `review_service.py`, route the new actions through the existing relationship decision endpoint, and update graph/export/UI code to use only current effective relationships by default. The manual review UI becomes name-first: company names are primary, technical IDs are secondary.

**Tech Stack:** Python 3.12, SQLite, FastAPI, Streamlit, pytest, ruff.

---

## File Map

- Create `src/trade_entity_graph/services/history_reuse_service.py`: classifies claims against effective historical curated relationships and returns history context.
- Modify `src/trade_entity_graph/services/review_service.py`: adds `keep_history_for_claim`, `supersede_history_with_claim`, and `mark_claim_pending_verify`.
- Modify `src/trade_entity_graph/services/relationship_service.py`: enriches candidate details with `history_context`.
- Modify `src/trade_entity_graph/services/graph_service.py`: includes `history_conflict` claim edges and excludes deprecated relationships.
- Modify `src/trade_entity_graph/services/export_service.py`: excludes deprecated and expired relationships from default exports.
- Modify `src/trade_entity_graph/services/entity_service.py`: counts only current effective curated relationships.
- Modify `src/trade_entity_graph/api/routers/imports.py`: runs history reuse after aggregation and returns counts.
- Modify `src/trade_entity_graph/api/routers/relationships.py`: routes new history-aware review actions.
- Modify `src/trade_entity_graph/ui/streamlit_app.py`: shows company names first in review context and moves IDs into secondary detail.
- Create `tests/test_history_reuse_service.py`: classification tests.
- Create `tests/test_history_review_service.py`: keep/supersede/pending review tests.
- Modify `tests/test_api_p0.py`: API import/decision coverage for history reuse.
- Modify `tests/test_services_p0_flow.py`: graph/export behavior for deprecated relationships.
- Modify `tests/test_streamlit_app.py`: name-first manual review helper tests.
- Modify `docs/superpowers/specs/2026-05-26-history-relationship-reuse-design.md`: convert to bilingual English/Chinese after implementation behavior is stable.

---

### Task 1: History Reuse Classification Service

**Files:**
- Create: `src/trade_entity_graph/services/history_reuse_service.py`
- Create: `tests/test_history_reuse_service.py`

- [ ] **Step 1: Write failing classification tests**

Create `tests/test_history_reuse_service.py`:

```python
from __future__ import annotations

from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.services.history_reuse_service import (
    apply_history_reuse_to_claims,
    get_history_context_for_claim,
)
from trade_entity_graph.utils.ids import new_id


def _insert_entity(connection, name: str) -> str:
    entity_id = new_id("ENT")
    connection.execute(
        """
        INSERT INTO entity (entity_id, canonical_name, entity_type)
        VALUES (?, ?, ?)
        """,
        (entity_id, name, "company"),
    )
    return entity_id


def _insert_claim(
    connection,
    from_entity_id: str,
    to_entity_id: str,
    *,
    candidate_relation_type: str = "trading_partner_candidate",
    confidence_level: str = "medium",
    confidence_score: float = 0.55,
    run_id: str = "RUN_HISTORY",
) -> str:
    claim_id = new_id("CLM")
    connection.execute(
        """
        INSERT INTO relationship_claim (
            claim_id, from_entity_id, to_entity_id, candidate_relation_type,
            relation_status, confidence_level, confidence_score, order_count,
            total_teu, recommendation_reason, run_id
        )
        VALUES (?, ?, ?, ?, 'candidate', ?, ?, 3, 12.5, '3 orders, 12.5 TEU', ?)
        """,
        (
            claim_id,
            from_entity_id,
            to_entity_id,
            candidate_relation_type,
            confidence_level,
            confidence_score,
            run_id,
        ),
    )
    return claim_id


def _insert_history(
    connection,
    from_entity_id: str,
    to_entity_id: str,
    *,
    relation_type: str,
    relation_status: str,
    valid_to: str | None = None,
) -> str:
    relationship_id = new_id("REL")
    connection.execute(
        """
        INSERT INTO curated_relationship (
            relationship_id, from_entity_id, to_entity_id, relation_type,
            relation_status, source_type, decision_note, verified_by, verified_at, valid_to
        )
        VALUES (?, ?, ?, ?, ?, 'manual', 'Historical review', 'reviewer', CURRENT_TIMESTAMP, ?)
        """,
        (
            relationship_id,
            from_entity_id,
            to_entity_id,
            relation_type,
            relation_status,
            valid_to,
        ),
    )
    return relationship_id


def _read_claim_status(db_path, claim_id: str) -> str:
    with get_connection(db_path) as connection:
        return connection.execute(
            "SELECT relation_status FROM relationship_claim WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()["relation_status"]


def test_compatible_positive_history_marks_claim_as_history_matched(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_claim(connection, acme, beta)
        history_id = _insert_history(
            connection,
            acme,
            beta,
            relation_type="trading_partner",
            relation_status="verified",
        )
        connection.commit()

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)
    context = get_history_context_for_claim(claim_id, db_path=db_path)

    assert result == {"history_matched": 1, "history_conflict": 0, "unchanged": 0}
    assert _read_claim_status(db_path, claim_id) == "history_matched"
    assert context is not None
    assert context["outcome"] == "history_matched"
    assert context["history_relationship"]["relationship_id"] == history_id
    assert "compatible historical relationship" in context["reason"]


def test_rejected_history_with_high_confidence_candidate_marks_conflict(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        acme = _insert_entity(connection, "ACME TRADING")
        omega = _insert_entity(connection, "OMEGA BUYER")
        claim_id = _insert_claim(connection, acme, omega, confidence_level="high")
        _insert_history(
            connection,
            acme,
            omega,
            relation_type="rejected_relation",
            relation_status="rejected",
        )
        connection.commit()

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)
    context = get_history_context_for_claim(claim_id, db_path=db_path)

    assert result == {"history_matched": 0, "history_conflict": 1, "unchanged": 0}
    assert _read_claim_status(db_path, claim_id) == "history_conflict"
    assert context is not None
    assert context["outcome"] == "history_conflict"
    assert "challenges rejected history" in context["reason"]


def test_rejected_history_with_low_confidence_candidate_stays_matched(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        acme = _insert_entity(connection, "ACME TRADING")
        omega = _insert_entity(connection, "OMEGA BUYER")
        claim_id = _insert_claim(
            connection,
            acme,
            omega,
            confidence_level="low",
            confidence_score=0.3,
        )
        _insert_history(
            connection,
            acme,
            omega,
            relation_type="rejected_relation",
            relation_status="rejected",
        )
        connection.commit()

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)

    assert result == {"history_matched": 1, "history_conflict": 0, "unchanged": 0}
    assert _read_claim_status(db_path, claim_id) == "history_matched"


def test_deprecated_history_is_ignored(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_claim(connection, acme, beta)
        _insert_history(
            connection,
            acme,
            beta,
            relation_type="trading_partner",
            relation_status="deprecated",
            valid_to="2026-05-01 00:00:00",
        )
        connection.commit()

    result = apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)

    assert result == {"history_matched": 0, "history_conflict": 0, "unchanged": 1}
    assert _read_claim_status(db_path, claim_id) == "candidate"


def test_symmetric_history_matches_reverse_pair(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        acme = _insert_entity(connection, "ACME TRADING")
        beta = _insert_entity(connection, "BETA FACTORY")
        claim_id = _insert_claim(connection, acme, beta)
        _insert_history(
            connection,
            beta,
            acme,
            relation_type="same_group",
            relation_status="verified",
        )
        connection.commit()

    apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)

    assert _read_claim_status(db_path, claim_id) == "history_matched"


def test_directional_history_does_not_match_reverse_pair(tmp_path) -> None:
    db_path = tmp_path / "history.db"
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        parent = _insert_entity(connection, "PARENT GROUP")
        child = _insert_entity(connection, "CHILD FACTORY")
        claim_id = _insert_claim(
            connection,
            child,
            parent,
            candidate_relation_type="factory_candidate",
        )
        _insert_history(
            connection,
            parent,
            child,
            relation_type="subsidiary",
            relation_status="verified",
        )
        connection.commit()

    apply_history_reuse_to_claims(run_id="RUN_HISTORY", db_path=db_path)

    assert _read_claim_status(db_path, claim_id) == "candidate"
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_history_reuse_service.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'trade_entity_graph.services.history_reuse_service'`.

- [ ] **Step 3: Implement history reuse service**

Create `src/trade_entity_graph/services/history_reuse_service.py`:

```python
"""History relationship reuse classification for relationship candidates."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from trade_entity_graph.db.connection import get_connection

CURRENT_EFFECTIVE_STATUSES = ("verified", "manual_only", "rejected")
POSITIVE_EFFECTIVE_STATUSES = ("verified", "manual_only")
REVIEWABLE_CLAIM_STATUSES = (
    "candidate",
    "history_matched",
    "history_conflict",
    "pending_verify",
)
CHALLENGE_REJECTED_CONFIDENCE_LEVELS = {"medium", "high"}
SYMMETRIC_RELATION_TYPES = {"same_entity", "same_group", "trading_partner"}
COMPATIBLE_RELATION_TYPES = {
    "trading_partner_candidate": {
        "trading_partner",
        "same_group",
        "subsidiary",
        "factory_node",
        "sales_center",
    },
    "factory_candidate": {"factory_node", "subsidiary", "same_group"},
    "sales_center_candidate": {"sales_center", "subsidiary", "same_group"},
    "same_group_candidate": {"same_group", "subsidiary", "same_entity"},
}


def _row_to_dict(row: Any | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _append_history_reason(current_reason: str | None, history_reason: str) -> str:
    base = (current_reason or "").split(" | history reuse:", 1)[0].strip()
    suffix = f"history reuse: {history_reason}"
    return f"{base} | {suffix}" if base else suffix


def _fetch_claim(connection, claim_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    return _row_to_dict(row)


def _fetch_effective_history(connection, claim: dict[str, Any]) -> list[dict[str, Any]]:
    status_placeholders = ", ".join("?" for _ in CURRENT_EFFECTIVE_STATUSES)
    symmetric_placeholders = ", ".join("?" for _ in SYMMETRIC_RELATION_TYPES)
    rows = connection.execute(
        f"""
        SELECT cr.*, e1.canonical_name AS from_name, e2.canonical_name AS to_name,
               CASE
                   WHEN cr.from_entity_id = ? AND cr.to_entity_id = ? THEN 0
                   ELSE 1
               END AS match_rank
        FROM curated_relationship cr
        JOIN entity e1 ON e1.entity_id = cr.from_entity_id
        JOIN entity e2 ON e2.entity_id = cr.to_entity_id
        WHERE cr.relation_status IN ({status_placeholders})
          AND cr.valid_to IS NULL
          AND (
              (cr.from_entity_id = ? AND cr.to_entity_id = ?)
              OR (
                  cr.from_entity_id = ?
                  AND cr.to_entity_id = ?
                  AND cr.relation_type IN ({symmetric_placeholders})
              )
          )
        ORDER BY match_rank, cr.verified_at DESC, cr.created_at DESC
        """,
        (
            claim["from_entity_id"],
            claim["to_entity_id"],
            *CURRENT_EFFECTIVE_STATUSES,
            claim["from_entity_id"],
            claim["to_entity_id"],
            claim["to_entity_id"],
            claim["from_entity_id"],
            *sorted(SYMMETRIC_RELATION_TYPES),
        ),
    ).fetchall()
    return [dict(row) for row in rows]


def _is_compatible(candidate_relation_type: str, history_relation_type: str) -> bool:
    compatible_types = COMPATIBLE_RELATION_TYPES.get(candidate_relation_type, set())
    return history_relation_type in compatible_types


def _classify(
    claim: dict[str, Any],
    history: dict[str, Any],
) -> tuple[str, str]:
    if history["relation_status"] == "rejected":
        confidence_level = claim["confidence_level"] or ""
        if confidence_level in CHALLENGE_REJECTED_CONFIDENCE_LEVELS:
            return (
                "history_conflict",
                (
                    "new medium/high confidence candidate challenges rejected history "
                    f"{history['relationship_id']}"
                ),
            )
        return (
            "history_matched",
            f"low confidence candidate keeps rejected history {history['relationship_id']}",
        )

    if _is_compatible(claim["candidate_relation_type"], history["relation_type"]):
        return (
            "history_matched",
            f"compatible historical relationship {history['relationship_id']} was found",
        )

    return (
        "history_conflict",
        (
            f"candidate type {claim['candidate_relation_type']} conflicts with historical "
            f"type {history['relation_type']} on {history['relationship_id']}"
        ),
    )


def classify_claim_against_history(
    connection,
    claim: dict[str, Any],
) -> dict[str, Any] | None:
    """Return history classification context for one claim."""

    histories = _fetch_effective_history(connection, claim)
    if not histories:
        return None

    history = histories[0]
    outcome, reason = _classify(claim, history)
    return {
        "claim_id": claim["claim_id"],
        "outcome": outcome,
        "reason": reason,
        "history_relationship": history,
    }


def get_history_context_for_claim(
    claim_id: str,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any] | None:
    """Return the effective historical relationship context for a claim."""

    with get_connection(db_path) as connection:
        claim = _fetch_claim(connection, claim_id)
        if claim is None:
            return None
        return classify_claim_against_history(connection, claim)


def apply_history_reuse_to_claims(
    *,
    run_id: str | None = None,
    db_path: str | Path | None = None,
) -> dict[str, int]:
    """Classify reviewable claims against current effective historical relationships."""

    counters = {"history_matched": 0, "history_conflict": 0, "unchanged": 0}
    status_placeholders = ", ".join("?" for _ in REVIEWABLE_CLAIM_STATUSES)
    params: list[Any] = [*REVIEWABLE_CLAIM_STATUSES]
    run_filter = ""
    if run_id:
        run_filter = "AND rc.run_id = ?"
        params.append(run_id)

    with get_connection(db_path) as connection:
        claims = connection.execute(
            f"""
            SELECT rc.*
            FROM relationship_claim rc
            WHERE rc.relation_status IN ({status_placeholders})
              {run_filter}
              AND NOT EXISTS (
                  SELECT 1
                  FROM curated_relationship cr
                  WHERE cr.decision_source = rc.claim_id
              )
            ORDER BY rc.created_at
            """,
            tuple(params),
        ).fetchall()

        for claim_row in claims:
            claim = dict(claim_row)
            context = classify_claim_against_history(connection, claim)
            if context is None:
                counters["unchanged"] += 1
                continue

            outcome = context["outcome"]
            counters[outcome] += 1
            connection.execute(
                """
                UPDATE relationship_claim
                SET relation_status = ?,
                    recommendation_reason = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE claim_id = ?
                """,
                (
                    outcome,
                    _append_history_reason(claim["recommendation_reason"], context["reason"]),
                    claim["claim_id"],
                ),
            )

        connection.commit()

    return counters
```

- [ ] **Step 4: Run classification tests to verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_history_reuse_service.py -q
```

Expected: all tests in `tests/test_history_reuse_service.py` PASS.

- [ ] **Step 5: Commit Task 1**

Run:

```powershell
git add src/trade_entity_graph/services/history_reuse_service.py tests/test_history_reuse_service.py
git commit -m "feat: classify claims against history"
```

---

### Task 2: History-Aware Review Mutations

**Files:**
- Modify: `src/trade_entity_graph/services/review_service.py`
- Create: `tests/test_history_review_service.py`

- [ ] **Step 1: Write failing review mutation tests**

Create `tests/test_history_review_service.py`:

```python
from __future__ import annotations

from trade_entity_graph.db.connection import get_connection, initialize_database
from trade_entity_graph.services.history_reuse_service import apply_history_reuse_to_claims
from trade_entity_graph.services.review_service import (
    keep_history_for_claim,
    mark_claim_pending_verify,
    supersede_history_with_claim,
)
from trade_entity_graph.utils.ids import new_id


def _seed_conflict(db_path):
    initialize_database(db_path)
    with get_connection(db_path) as connection:
        acme = new_id("ENT")
        omega = new_id("ENT")
        connection.execute(
            "INSERT INTO entity (entity_id, canonical_name) VALUES (?, ?)",
            (acme, "ACME TRADING"),
        )
        connection.execute(
            "INSERT INTO entity (entity_id, canonical_name) VALUES (?, ?)",
            (omega, "OMEGA BUYER"),
        )
        old_relationship_id = new_id("REL")
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, source_type, decision_note, verified_by, verified_at
            )
            VALUES (?, ?, ?, 'rejected_relation', 'rejected', 'manual',
                    'Earlier review rejected this pair', 'old_reviewer', CURRENT_TIMESTAMP)
            """,
            (old_relationship_id, acme, omega),
        )
        claim_id = new_id("CLM")
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason, run_id
            )
            VALUES (?, ?, ?, 'trading_partner_candidate', 'candidate',
                    'high', 0.8, 8, 36.0, '8 orders, 36 TEU', 'RUN_CONFLICT')
            """,
            (claim_id, acme, omega),
        )
        connection.commit()

    apply_history_reuse_to_claims(run_id="RUN_CONFLICT", db_path=db_path)
    return claim_id, old_relationship_id


def test_keep_history_records_decision_without_new_curated_relationship(tmp_path) -> None:
    db_path = tmp_path / "review.db"
    claim_id, old_relationship_id = _seed_conflict(db_path)

    result = keep_history_for_claim(
        claim_id,
        reason="Historical rejection still applies",
        operator="reviewer",
        db_path=db_path,
    )

    assert result["claim_id"] == claim_id
    assert result["relation_status"] == "history_matched"
    assert result["history_relationship_id"] == old_relationship_id
    with get_connection(db_path) as connection:
        curated_count = connection.execute(
            "SELECT COUNT(*) FROM curated_relationship"
        ).fetchone()[0]
        decision = connection.execute(
            """
            SELECT * FROM relationship_decision
            WHERE claim_id = ? AND action_type = 'keep_history'
            """,
            (claim_id,),
        ).fetchone()
        audit_count = connection.execute(
            """
            SELECT COUNT(*) FROM audit_log
            WHERE object_type = 'relationship_claim' AND object_id = ?
            """,
            (claim_id,),
        ).fetchone()[0]

    assert curated_count == 1
    assert decision["relationship_id"] == old_relationship_id
    assert decision["after_status"] == "history_matched"
    assert audit_count == 1


def test_supersede_history_deprecates_old_and_creates_new_relationship(tmp_path) -> None:
    db_path = tmp_path / "review.db"
    claim_id, old_relationship_id = _seed_conflict(db_path)

    new_relationship = supersede_history_with_claim(
        claim_id,
        old_relationship_id=old_relationship_id,
        relation_type="trading_partner",
        reason="New shipment evidence proves the relationship",
        operator="reviewer",
        db_path=db_path,
    )

    assert new_relationship["relation_status"] == "verified"
    assert new_relationship["relation_type"] == "trading_partner"
    assert new_relationship["supersedes_relationship_id"] == old_relationship_id
    with get_connection(db_path) as connection:
        old_relationship = connection.execute(
            "SELECT * FROM curated_relationship WHERE relationship_id = ?",
            (old_relationship_id,),
        ).fetchone()
        decision = connection.execute(
            """
            SELECT * FROM relationship_decision
            WHERE claim_id = ? AND action_type = 'supersede'
            """,
            (claim_id,),
        ).fetchone()
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM audit_log WHERE action_type IN ('deprecated', 'supersede')"
        ).fetchone()[0]

    assert old_relationship["relation_status"] == "deprecated"
    assert old_relationship["valid_to"] is not None
    assert decision["relationship_id"] == new_relationship["relationship_id"]
    assert decision["before_status"] == "rejected"
    assert decision["after_status"] == "verified"
    assert audit_count == 2


def test_mark_pending_verify_leaves_history_unchanged(tmp_path) -> None:
    db_path = tmp_path / "review.db"
    claim_id, old_relationship_id = _seed_conflict(db_path)

    result = mark_claim_pending_verify(
        claim_id,
        reason="Need sales team confirmation",
        operator="reviewer",
        db_path=db_path,
    )

    assert result["relation_status"] == "pending_verify"
    with get_connection(db_path) as connection:
        old_relationship = connection.execute(
            "SELECT relation_status FROM curated_relationship WHERE relationship_id = ?",
            (old_relationship_id,),
        ).fetchone()
        decision = connection.execute(
            """
            SELECT * FROM relationship_decision
            WHERE claim_id = ? AND action_type = 'mark_pending_verify'
            """,
            (claim_id,),
        ).fetchone()

    assert old_relationship["relation_status"] == "rejected"
    assert decision["after_status"] == "pending_verify"
```

- [ ] **Step 2: Run review tests to verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_history_review_service.py -q
```

Expected: FAIL with imports missing from `trade_entity_graph.services.review_service`.

- [ ] **Step 3: Add history-aware review functions**

Modify `src/trade_entity_graph/services/review_service.py`:

```python
from trade_entity_graph.services.history_reuse_service import get_history_context_for_claim
```

Add these helper functions below `_write_decision_and_audit`:

```python
def _write_claim_decision_and_audit(
    connection,
    *,
    relationship_id: str | None,
    claim_id: str,
    action_type: str,
    before_relation_type: str | None,
    after_relation_type: str | None,
    before_status: str | None,
    after_status: str,
    reason: str,
    operator: str,
) -> None:
    connection.execute(
        """
        INSERT INTO relationship_decision (
            decision_id, relationship_id, claim_id, action_type, before_relation_type,
            after_relation_type, before_status, after_status, reason, operator
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("DEC"),
            relationship_id,
            claim_id,
            action_type,
            before_relation_type,
            after_relation_type,
            before_status,
            after_status,
            reason,
            operator,
        ),
    )
    connection.execute(
        """
        INSERT INTO audit_log (
            audit_id, object_type, object_id, action_type, before_value,
            after_value, operator, reason
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            new_id("AUD"),
            "relationship_claim",
            claim_id,
            action_type,
            before_status,
            after_status,
            operator,
            reason,
        ),
    )


def _fetch_claim(connection, claim_id: str):
    claim = connection.execute(
        "SELECT * FROM relationship_claim WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    if not claim:
        raise ValueError(f"Unknown relationship claim: {claim_id}")
    return claim


def _resolve_history_relationship_id(
    claim_id: str,
    *,
    db_path: str | Path | None,
    old_relationship_id: str | None = None,
) -> str:
    if old_relationship_id:
        return old_relationship_id
    context = get_history_context_for_claim(claim_id, db_path=db_path)
    if not context:
        raise ValueError(f"No effective historical relationship found for claim: {claim_id}")
    return context["history_relationship"]["relationship_id"]
```

Add these public functions at the end of `review_service.py`:

```python
def keep_history_for_claim(
    claim_id: str,
    *,
    reason: str,
    operator: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Keep the effective historical conclusion for a conflicting claim."""

    old_relationship_id = _resolve_history_relationship_id(claim_id, db_path=db_path)
    with get_connection(db_path) as connection:
        claim = _fetch_claim(connection, claim_id)
        history = connection.execute(
            "SELECT * FROM curated_relationship WHERE relationship_id = ?",
            (old_relationship_id,),
        ).fetchone()
        connection.execute(
            """
            UPDATE relationship_claim
            SET relation_status = 'history_matched', updated_at = CURRENT_TIMESTAMP
            WHERE claim_id = ?
            """,
            (claim_id,),
        )
        _write_claim_decision_and_audit(
            connection,
            relationship_id=old_relationship_id,
            claim_id=claim_id,
            action_type="keep_history",
            before_relation_type=claim["candidate_relation_type"],
            after_relation_type=history["relation_type"],
            before_status=claim["relation_status"],
            after_status="history_matched",
            reason=reason,
            operator=operator,
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM relationship_claim WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()
        result = dict(row)
        result["history_relationship_id"] = old_relationship_id
        return result


def supersede_history_with_claim(
    claim_id: str,
    *,
    old_relationship_id: str | None = None,
    relation_type: str,
    reason: str,
    operator: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Replace an effective historical relationship with a new curated relationship."""

    resolved_old_relationship_id = _resolve_history_relationship_id(
        claim_id,
        db_path=db_path,
        old_relationship_id=old_relationship_id,
    )
    with get_connection(db_path) as connection:
        claim = _fetch_claim(connection, claim_id)
        old_relationship = connection.execute(
            """
            SELECT * FROM curated_relationship
            WHERE relationship_id = ?
              AND relation_status IN ('verified', 'manual_only', 'rejected')
              AND valid_to IS NULL
            """,
            (resolved_old_relationship_id,),
        ).fetchone()
        if not old_relationship:
            raise ValueError(
                f"Historical relationship is not current effective: {resolved_old_relationship_id}"
            )

        connection.execute(
            """
            UPDATE curated_relationship
            SET relation_status = 'deprecated',
                valid_to = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE relationship_id = ?
            """,
            (resolved_old_relationship_id,),
        )
        connection.execute(
            """
            INSERT INTO audit_log (
                audit_id, object_type, object_id, action_type, before_value,
                after_value, operator, reason
            )
            VALUES (?, 'curated_relationship', ?, 'deprecated', ?, 'deprecated', ?, ?)
            """,
            (
                new_id("AUD"),
                resolved_old_relationship_id,
                old_relationship["relation_status"],
                operator,
                reason,
            ),
        )

        relationship_id = new_id("REL")
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, confidence_level, confidence_score, source_type,
                decision_source, decision_note, verified_by, verified_at, valid_from,
                supersedes_relationship_id
            )
            VALUES (?, ?, ?, ?, 'verified', ?, ?, 'claim', ?, ?, ?, CURRENT_TIMESTAMP,
                    CURRENT_TIMESTAMP, ?)
            """,
            (
                relationship_id,
                claim["from_entity_id"],
                claim["to_entity_id"],
                relation_type,
                claim["confidence_level"],
                claim["confidence_score"],
                claim_id,
                reason,
                operator,
                resolved_old_relationship_id,
            ),
        )
        _write_decision_and_audit(
            connection,
            relationship_id=relationship_id,
            claim_id=claim_id,
            action_type="supersede",
            before_relation_type=old_relationship["relation_type"],
            after_relation_type=relation_type,
            before_status=old_relationship["relation_status"],
            after_status="verified",
            reason=reason,
            operator=operator,
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM curated_relationship WHERE relationship_id = ?",
            (relationship_id,),
        ).fetchone()
        return dict(row)


def mark_claim_pending_verify(
    claim_id: str,
    *,
    reason: str,
    operator: str,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    """Mark a claim for later verification without changing historical relationships."""

    with get_connection(db_path) as connection:
        claim = _fetch_claim(connection, claim_id)
        connection.execute(
            """
            UPDATE relationship_claim
            SET relation_status = 'pending_verify', updated_at = CURRENT_TIMESTAMP
            WHERE claim_id = ?
            """,
            (claim_id,),
        )
        _write_claim_decision_and_audit(
            connection,
            relationship_id=None,
            claim_id=claim_id,
            action_type="mark_pending_verify",
            before_relation_type=claim["candidate_relation_type"],
            after_relation_type=claim["candidate_relation_type"],
            before_status=claim["relation_status"],
            after_status="pending_verify",
            reason=reason,
            operator=operator,
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM relationship_claim WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()
        return dict(row)
```

- [ ] **Step 4: Run review tests to verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_history_review_service.py -q
```

Expected: all tests in `tests/test_history_review_service.py` PASS.

- [ ] **Step 5: Run existing P0 service flow tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_services_p0_flow.py -q
```

Expected: all tests in `tests/test_services_p0_flow.py` PASS.

- [ ] **Step 6: Commit Task 2**

Run:

```powershell
git add src/trade_entity_graph/services/review_service.py tests/test_history_review_service.py
git commit -m "feat: review history conflicts"
```

---

### Task 3: Relationship Detail And API Integration

**Files:**
- Modify: `src/trade_entity_graph/services/relationship_service.py`
- Modify: `src/trade_entity_graph/api/routers/imports.py`
- Modify: `src/trade_entity_graph/api/routers/relationships.py`
- Modify: `tests/test_api_p0.py`

- [ ] **Step 1: Write failing API expectations**

Modify `tests/test_api_p0.py` inside `test_api_p0_import_search_review_graph_export` after the first import response assertion:

```python
    assert import_payload["history_reuse"] == {
        "history_matched": 0,
        "history_conflict": 0,
        "unchanged": 3,
    }
```

Modify the relationship detail assertions:

```python
    assert relationship_payload["record_type"] == "relationship_claim"
    assert relationship_payload["from_name"] == "ACME TRADING"
    assert relationship_payload["to_name"]
    assert "history_context" in relationship_payload
```

Add this second API test to `tests/test_api_p0.py`:

```python
def test_api_history_conflict_can_keep_history(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "api-history.db"
    monkeypatch.setenv("TEG_DATABASE_PATH", str(db_path))

    from trade_entity_graph.db.connection import get_connection, initialize_database
    from trade_entity_graph.api.main import create_app
    from trade_entity_graph.utils.ids import new_id

    initialize_database(db_path)
    with get_connection(db_path) as connection:
        acme = new_id("ENT")
        omega = new_id("ENT")
        connection.execute(
            "INSERT INTO entity (entity_id, canonical_name) VALUES (?, ?)",
            (acme, "ACME TRADING"),
        )
        connection.execute(
            "INSERT INTO entity (entity_id, canonical_name) VALUES (?, ?)",
            (omega, "OMEGA BUYER"),
        )
        connection.execute(
            """
            INSERT INTO curated_relationship (
                relationship_id, from_entity_id, to_entity_id, relation_type,
                relation_status, source_type, verified_by, verified_at
            )
            VALUES ('REL_HISTORY', ?, ?, 'rejected_relation', 'rejected',
                    'manual', 'reviewer', CURRENT_TIMESTAMP)
            """,
            (acme, omega),
        )
        connection.execute(
            """
            INSERT INTO relationship_claim (
                claim_id, from_entity_id, to_entity_id, candidate_relation_type,
                relation_status, confidence_level, confidence_score, order_count,
                total_teu, recommendation_reason
            )
            VALUES ('CLM_CONFLICT', ?, ?, 'trading_partner_candidate', 'history_conflict',
                    'high', 0.8, 5, 22.0, '5 orders, 22 TEU')
            """,
            (acme, omega),
        )
        connection.commit()

    app = create_app()

    status, detail_payload = _request(app, "GET", "/relationships/CLM_CONFLICT")
    assert status == 200
    assert detail_payload["from_name"] == "ACME TRADING"
    assert detail_payload["to_name"] == "OMEGA BUYER"
    assert detail_payload["history_context"]["history_relationship"]["relationship_id"] == (
        "REL_HISTORY"
    )

    status, decision_payload = _request(
        app,
        "POST",
        "/relationships/CLM_CONFLICT/decision",
        json_body={
            "action_type": "keep_history",
            "reason": "History remains correct",
            "operator": "tester",
        },
    )
    assert status == 200
    assert decision_payload["relation_status"] == "history_matched"
```

- [ ] **Step 2: Run API tests to verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_api_p0.py -q
```

Expected: FAIL because `history_reuse` and new decision actions are not wired.

- [ ] **Step 3: Enrich relationship detail with history context**

Modify imports in `src/trade_entity_graph/services/relationship_service.py`:

```python
from trade_entity_graph.services.history_reuse_service import get_history_context_for_claim
```

Modify the candidate branch in `get_relationship_detail`:

```python
        if row:
            result = dict(row)
            if result["record_type"] == "relationship_claim":
                result["history_context"] = get_history_context_for_claim(
                    relationship_id,
                    db_path=db_path,
                )
            return result
        return None
```

Ensure the curated relationship branch returns a consistent key:

```python
        if row:
            result = dict(row)
            result["history_context"] = None
            return result
```

- [ ] **Step 4: Run history reuse from the import endpoint**

Modify imports in `src/trade_entity_graph/api/routers/imports.py`:

```python
from trade_entity_graph.services.history_reuse_service import apply_history_reuse_to_claims
```

Modify the aggregation block:

```python
    history_reuse = {"history_matched": 0, "history_conflict": 0, "unchanged": 0}
    if request.aggregate_claims:
        claim_count = aggregate_relationship_claims(run_id=result.run_id)["claim_count"]
        history_reuse = apply_history_reuse_to_claims(run_id=result.run_id)
```

Add to the response dict:

```python
        "history_reuse": history_reuse,
```

- [ ] **Step 5: Route new decision actions**

Modify imports in `src/trade_entity_graph/api/routers/relationships.py`:

```python
from trade_entity_graph.services.review_service import (
    create_manual_relationship,
    decide_relationship,
    keep_history_for_claim,
    mark_claim_pending_verify,
    supersede_history_with_claim,
)
```

Modify `DecisionRequest`:

```python
class DecisionRequest(BaseModel):
    action_type: str
    relation_type: str | None = None
    reason: str
    operator: str
    old_relationship_id: str | None = None
```

Replace `decide_relationship_endpoint` body:

```python
    if request.action_type == "keep_history":
        return keep_history_for_claim(
            relationship_id,
            reason=request.reason,
            operator=request.operator,
        )
    if request.action_type == "mark_pending_verify":
        return mark_claim_pending_verify(
            relationship_id,
            reason=request.reason,
            operator=request.operator,
        )
    if request.action_type == "supersede_history":
        if not request.relation_type:
            raise HTTPException(
                status_code=422,
                detail="relation_type is required for supersede_history",
            )
        return supersede_history_with_claim(
            relationship_id,
            old_relationship_id=request.old_relationship_id,
            relation_type=request.relation_type,
            reason=request.reason,
            operator=request.operator,
        )
    if not request.relation_type:
        raise HTTPException(status_code=422, detail="relation_type is required")
    return decide_relationship(
        relationship_id,
        action_type=request.action_type,
        relation_type=request.relation_type,
        reason=request.reason,
        operator=request.operator,
    )
```

- [ ] **Step 6: Run API tests to verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_api_p0.py -q
```

Expected: all tests in `tests/test_api_p0.py` PASS.

- [ ] **Step 7: Commit Task 3**

Run:

```powershell
git add src/trade_entity_graph/services/relationship_service.py src/trade_entity_graph/api/routers/imports.py src/trade_entity_graph/api/routers/relationships.py tests/test_api_p0.py
git commit -m "feat: expose history reuse through api"
```

---

### Task 4: Current-Effective Filtering In Graphs And Exports

**Files:**
- Modify: `src/trade_entity_graph/services/graph_service.py`
- Modify: `src/trade_entity_graph/services/export_service.py`
- Modify: `src/trade_entity_graph/services/entity_service.py`
- Modify: `tests/test_services_p0_flow.py`

- [ ] **Step 1: Write failing current-effective tests**

Add this test to `tests/test_services_p0_flow.py`:

```python
def test_deprecated_relationship_is_hidden_from_graph_export_and_entity_counts(tmp_path) -> None:
    db_path = _seed_p0_flow(tmp_path)
    acme_id = _entity_id(db_path, "ACME TRADING")
    claim_id = _claim_id(db_path, "ACME TRADING", "BETA FACTORY")

    old_relationship = decide_relationship(
        claim_id,
        action_type="confirm",
        relation_type="trading_partner",
        reason="Old conclusion",
        operator="tester",
        db_path=db_path,
    )
    with get_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE curated_relationship
            SET relation_status = 'deprecated', valid_to = CURRENT_TIMESTAMP
            WHERE relationship_id = ?
            """,
            (old_relationship["relationship_id"],),
        )
        connection.commit()

    graph = get_ego_graph(acme_id, db_path=db_path, include_rejected=True)
    exported = export_relationship_rows(acme_id, db_path=db_path, include_rejected=True)
    detail = get_entity_detail(acme_id, db_path=db_path)

    assert all(edge["id"] != old_relationship["relationship_id"] for edge in graph["edges"])
    assert all(row["relationship_id"] != old_relationship["relationship_id"] for row in exported)
    assert detail["curated_relationship_count"] == 0
```

Add this test to `tests/test_services_p0_flow.py`:

```python
def test_ego_graph_includes_history_conflict_claim_edges(tmp_path) -> None:
    db_path = _seed_p0_flow(tmp_path)
    acme_id = _entity_id(db_path, "ACME TRADING")
    claim_id = _claim_id(db_path, "ACME TRADING", "BETA FACTORY")
    with get_connection(db_path) as connection:
        connection.execute(
            """
            UPDATE relationship_claim
            SET relation_status = 'history_conflict'
            WHERE claim_id = ?
            """,
            (claim_id,),
        )
        connection.commit()

    graph = get_ego_graph(acme_id, db_path=db_path)

    assert any(
        edge["id"] == claim_id
        and edge["edge_type"] == "relationship_claim"
        and edge["status"] == "history_conflict"
        for edge in graph["edges"]
    )
```

- [ ] **Step 2: Run focused tests to verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_services_p0_flow.py::test_deprecated_relationship_is_hidden_from_graph_export_and_entity_counts tests\test_services_p0_flow.py::test_ego_graph_includes_history_conflict_claim_edges -q
```

Expected: FAIL because deprecated rows are still visible or `history_conflict` claims are not graph candidates.

- [ ] **Step 3: Update graph candidate and curated filters**

Modify `src/trade_entity_graph/services/graph_service.py`:

```python
PENDING_CLAIM_STATUSES = ("candidate", "pending_verify", "history_conflict")
```

Add current-effective filters to both curated relationship SQL branches:

```sql
AND cr.valid_to IS NULL
AND cr.relation_status != 'deprecated'
```

For the branch that hides rejected relationships, keep:

```sql
AND cr.relation_status != 'rejected'
```

- [ ] **Step 4: Update export and entity count filters**

Modify `src/trade_entity_graph/services/export_service.py`:

```python
    status_filter = "" if include_rejected else "AND cr.relation_status != 'rejected'"
```

Replace it with:

```python
    rejected_filter = "" if include_rejected else "AND cr.relation_status != 'rejected'"
```

Then update the SQL WHERE clause:

```sql
WHERE (cr.from_entity_id = ? OR cr.to_entity_id = ?)
  AND cr.valid_to IS NULL
  AND cr.relation_status != 'deprecated'
{rejected_filter}
```

Modify `src/trade_entity_graph/services/entity_service.py` curated count query:

```sql
SELECT COUNT(*) FROM curated_relationship
WHERE (from_entity_id = ? OR to_entity_id = ?)
  AND valid_to IS NULL
  AND relation_status != 'deprecated'
```

- [ ] **Step 5: Run focused tests to verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_services_p0_flow.py::test_deprecated_relationship_is_hidden_from_graph_export_and_entity_counts tests\test_services_p0_flow.py::test_ego_graph_includes_history_conflict_claim_edges -q
```

Expected: both tests PASS.

- [ ] **Step 6: Run graph and export regression tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_services_p0_flow.py tests\test_demo_acceptance.py -q
```

Expected: all tests in both files PASS.

- [ ] **Step 7: Commit Task 4**

Run:

```powershell
git add src/trade_entity_graph/services/graph_service.py src/trade_entity_graph/services/export_service.py src/trade_entity_graph/services/entity_service.py tests/test_services_p0_flow.py
git commit -m "fix: use current effective relationships"
```

---

### Task 5: Name-First Manual Review UI

**Files:**
- Modify: `src/trade_entity_graph/ui/streamlit_app.py`
- Modify: `tests/test_streamlit_app.py`

- [ ] **Step 1: Write failing UI helper tests**

Add these tests to `tests/test_streamlit_app.py`:

```python
def test_manual_review_context_is_name_first_without_primary_entity_ids() -> None:
    detail = {
        "claim_id": "CLM_1",
        "record_type": "relationship_claim",
        "from_entity_id": "ENT_A",
        "from_name": "ACME TRADING",
        "to_entity_id": "ENT_B",
        "to_name": "BETA FACTORY",
        "candidate_relation_type": "trading_partner_candidate",
        "relation_status": "history_conflict",
        "confidence_level": "high",
        "confidence_score": 0.8,
        "order_count": 5,
        "total_teu": 22.0,
        "recommendation_reason": "5 orders, 22 TEU",
        "history_context": {
            "outcome": "history_conflict",
            "reason": "new medium/high confidence candidate challenges rejected history REL_1",
            "history_relationship": {
                "relationship_id": "REL_1",
                "relation_type": "rejected_relation",
                "relation_status": "rejected",
                "verified_by": "reviewer",
                "verified_at": "2026-05-25 10:00:00",
                "decision_note": "Earlier rejection",
            },
        },
    }

    summary = streamlit_app.format_manual_review_context(detail)

    assert "主体 A：ACME TRADING" in summary
    assert "主体 B：BETA FACTORY" in summary
    assert "新候选关系：trading_partner_candidate" in summary
    assert "历史结论：rejected_relation / rejected" in summary
    assert "冲突原因：" in summary
    assert "ENT_A" not in summary
    assert "ENT_B" not in summary


def test_technical_identifier_summary_keeps_ids_secondary() -> None:
    detail = {
        "claim_id": "CLM_1",
        "from_entity_id": "ENT_A",
        "to_entity_id": "ENT_B",
        "history_context": {
            "history_relationship": {"relationship_id": "REL_1"},
        },
    }

    summary = streamlit_app.format_technical_identifier_summary(detail)

    assert "claim_id：CLM_1" in summary
    assert "history_relationship_id：REL_1" in summary
    assert "from_entity_id：ENT_A" in summary
    assert "to_entity_id：ENT_B" in summary
```

- [ ] **Step 2: Run UI helper tests to verify they fail**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_streamlit_app.py::test_manual_review_context_is_name_first_without_primary_entity_ids tests\test_streamlit_app.py::test_technical_identifier_summary_keeps_ids_secondary -q
```

Expected: FAIL because helper functions are missing.

- [ ] **Step 3: Add name-first helper functions**

Add to `src/trade_entity_graph/ui/streamlit_app.py` near existing formatting helpers:

```python
def format_manual_review_context(detail: dict[str, Any] | None) -> str:
    """Return business-facing review context with company names as primary content."""

    if not detail:
        return "未找到候选关系或最终关系，请检查 ID 是否正确。"

    history_context = detail.get("history_context") or {}
    history_relationship = history_context.get("history_relationship") or {}
    relation_type = detail.get("candidate_relation_type") or detail.get("relation_type") or "-"
    relation_status = detail.get("relation_status") or "-"
    confidence_level = detail.get("confidence_level") or "-"
    confidence_score = detail.get("confidence_score")
    order_count = detail.get("order_count") or 0
    total_teu = detail.get("total_teu") or 0
    reason = detail.get("recommendation_reason") or "-"
    lines = [
        f"主体 A：{detail.get('from_name') or '-'}",
        f"主体 B：{detail.get('to_name') or '-'}",
        f"新候选关系：{relation_type}",
        f"候选状态：{relation_status}",
        f"置信度：{confidence_level} / {confidence_score if confidence_score is not None else '-'}",
        f"订单证据：{order_count} orders / {total_teu:g} TEU",
        f"推荐理由：{reason}",
    ]
    if history_relationship:
        lines.extend(
            [
                (
                    "历史结论："
                    f"{history_relationship.get('relation_type') or '-'} / "
                    f"{history_relationship.get('relation_status') or '-'}"
                ),
                f"历史审核人：{history_relationship.get('verified_by') or '-'}",
                f"历史审核时间：{history_relationship.get('verified_at') or '-'}",
                f"历史备注：{history_relationship.get('decision_note') or '-'}",
                f"冲突原因：{history_context.get('reason') or '-'}",
            ]
        )
    return "\n\n".join(lines)


def format_technical_identifier_summary(detail: dict[str, Any] | None) -> str:
    """Return technical IDs for secondary inspection."""

    if not detail:
        return ""
    history_context = detail.get("history_context") or {}
    history_relationship = history_context.get("history_relationship") or {}
    values = {
        "claim_id": detail.get("claim_id"),
        "relationship_id": detail.get("relationship_id"),
        "history_relationship_id": history_relationship.get("relationship_id"),
        "from_entity_id": detail.get("from_entity_id"),
        "to_entity_id": detail.get("to_entity_id"),
    }
    return "\n".join(f"{key}：{value}" for key, value in values.items() if value)
```

- [ ] **Step 4: Use helpers in `render_review_tab`**

Modify the claim detail block in `render_review_tab`:

```python
    relationship_detail = None
    if claim_id:
        relationship_detail = get_relationship_detail(claim_id)
        st.markdown(format_manual_review_context(relationship_detail))
        technical_summary = format_technical_identifier_summary(relationship_detail)
        if technical_summary:
            with st.expander("查看技术 ID"):
                st.code(technical_summary)
```

Replace the existing `st.json(relationship_detail)` primary display. Keep JSON only under the same expander when it is useful:

```python
                st.json(relationship_detail)
```

- [ ] **Step 5: Add history-aware action labels**

In `render_review_tab`, add a mapping before the action selectbox:

```python
    history_context = (relationship_detail or {}).get("history_context") or {}
    if history_context:
        action_label_by_type = {
            "keep_history": "沿用历史结论",
            "supersede_history": "接受新证据，替代历史结论",
            "mark_pending_verify": "暂不判断，标记待验证",
        }
    else:
        action_label_by_type = {
            "confirm": "确认候选关系",
            "reject": "否定候选关系",
            "modify": "修改关系类型并确认",
        }
    selected_action_label = st.selectbox("审核动作", list(action_label_by_type.values()))
    action_type = next(
        key for key, value in action_label_by_type.items() if value == selected_action_label
    )
```

Keep `relation_type` selectbox visible for `confirm`, `modify`, `reject`, and `supersede_history`. For `keep_history` and `mark_pending_verify`, do not require relation type.

- [ ] **Step 6: Run UI tests to verify they pass**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_streamlit_app.py -q
```

Expected: all tests in `tests/test_streamlit_app.py` PASS.

- [ ] **Step 7: Commit Task 5**

Run:

```powershell
git add src/trade_entity_graph/ui/streamlit_app.py tests/test_streamlit_app.py
git commit -m "feat: show review entity names first"
```

---

### Task 6: Bilingual Design Spec Update

**Files:**
- Modify: `docs/superpowers/specs/2026-05-26-history-relationship-reuse-design.md`

- [ ] **Step 1: Add bilingual format note and Chinese title**

At the top of `docs/superpowers/specs/2026-05-26-history-relationship-reuse-design.md`, replace the title with:

```markdown
# History Relationship Reuse And Conflict Review Design / 历史关系复用与冲突复核设计

> Format: each major section keeps the English design first, followed by a Chinese counterpart.
> 格式说明：每个主要章节先保留英文设计，再提供中文对照说明。
```

- [ ] **Step 2: Add Chinese counterpart for the Goal section**

After the existing English `## Goal` section, add:

```markdown
## 目标

为 MVP 的关系审核闭环增加历史关系复用能力。新导入数据生成关系候选后，系统会把这些候选与当前有效的历史人工审核结论进行比对：与历史一致的候选标记为历史命中，与历史冲突的候选进入人工复核。

本功能遵循一个核心原则：历史审核结论是可复用的数据资产，但不是不可挑战的铁律。如果新导入证据证明历史结论有误，操作人可以用新的最终关系替代旧结论，同时将旧结论保留为可追溯的 deprecated 历史版本。
```

- [ ] **Step 3: Add Chinese counterpart for the Scope section**

After the English `## Scope` section, add:

```markdown
## 范围

包含：

- 将历史复用状态持久化到 `relationship_claim`，不新增独立 reconciliation 表。
- 将新候选标记为普通候选、历史命中或历史冲突。
- 支持人工选择沿用历史、接受新证据并替代历史、或标记为待验证。
- 被替代的旧最终关系保留为 `deprecated`。
- 新最终关系通过 `supersedes_relationship_id` 指向旧关系。
- 人工审核页面优先展示业务主体名称。
- `entity_id` 和 `claim_id` 保留为技术标识，但不作为主要审核上下文。
- 增加服务层与 UI 测试，覆盖匹配、冲突、替代和名称优先展示。

不包含：

- 不自动替代历史结论。
- 不新增复杂审批流。
- 第一版不新增独立 reconciliation 表。
- 不接入外部公开企业验证。
- 不扩展二跳图谱或路径搜索。
- 不重写 React 前端或做大型 UI 改版。
```

- [ ] **Step 4: Add Chinese counterpart for the remaining design sections**

For each remaining English section, insert the following Chinese section immediately after it:

```markdown
## 选定方案

使用 `relationship_claim.relation_status` 记录历史复用结果，使该功能继续沿用现有主流程：

```text
导入 -> 订单角色边 -> 关系候选 -> 人工审核 -> 最终关系
```

拒绝的替代方案：

- 只做 UI 临时提示虽然开发最快，但结果不可持久化，也无法形成复核队列。
- 新增独立 `relationship_reconciliation` 表更适合未来的数据治理模块，但对于当前 MVP 偏重。

## 数据模型语义

第一版不新增表。

候选状态：

- `candidate`：没有命中有效历史关系的普通新候选。
- `history_matched`：命中有效历史结论，通常不需要重复审核。
- `history_conflict`：与有效历史结论冲突，需要人工复核。
- `pending_verify`：复核人暂不判断，需要后续验证。

最终关系状态：

- `verified`：当前有效的已确认关系。
- `manual_only`：人工直接新增且当前有效的关系。
- `rejected`：当前有效的否定结论。
- `deprecated`：已被新版关系替代的历史结论。

当前有效关系定义为：

```sql
relation_status IN ('verified', 'manual_only', 'rejected')
AND valid_to IS NULL
```

`deprecated` 不参与默认图谱、导出和自动复用，只在历史详情中保留。

## 历史匹配规则

第一版使用确定性、可解释规则，绝不自动替代历史结论。

- 只匹配当前有效的历史关系。
- `same_entity`、`same_group`、`trading_partner` 支持反向匹配。
- `subsidiary`、`factory_node`、`sales_center`、`logistics_service` 第一版按有向关系匹配。
- 有效正向历史关系与兼容候选匹配时，标记为 `history_matched`。
- 有效正向历史关系与不兼容候选匹配时，标记为 `history_conflict`。
- 有效否定历史关系遇到 medium/high 置信度的新正向候选时，标记为 `history_conflict`。
- 有效否定历史关系遇到 low 置信度的新候选时，标记为 `history_matched`。

## 复核流程

历史冲突仍在现有“人工审核”页面处理，不新增单独页面。

复核动作：

- `keep_history`：沿用历史结论，不新增最终关系，只记录决策。
- `supersede_history`：接受新导入证据，将旧关系标记为 `deprecated`，新增当前有效关系，并用 `supersedes_relationship_id` 串联旧版本。
- `mark_pending_verify`：暂不判断，将候选标记为 `pending_verify`，不改变历史关系。

## 服务与 API

新增历史复用服务负责候选分类；审核服务负责写入人工复核决策。导入接口在候选聚合后调用历史复用检查，并返回 `history_reuse` 统计。关系详情接口返回主体名称和历史上下文，便于人工审核页面展示。

## UI

人工审核页面必须名称优先展示：

- `主体 A：<canonical_name>`
- `主体 B：<canonical_name>`
- `新候选关系：<candidate_relation_type>`
- `历史结论：<relation_type> / <relation_status>`
- `冲突原因：<plain language explanation>`

技术 ID 放到折叠区或次要信息中：

- `claim_id`
- `relationship_id`
- `from_entity_id`
- `to_entity_id`

## 测试策略

测试覆盖服务分类、人工复核、API 透出、图谱/导出过滤以及人工审核页面名称优先展示。关键验收点是：历史命中可持久化，历史冲突可复核，替代历史时旧关系可追溯且默认不再参与当前有效结果。
```

- [ ] **Step 5: Verify bilingual spec formatting**

Run:

```powershell
git diff --check -- docs\superpowers\specs\2026-05-26-history-relationship-reuse-design.md
```

Expected: `git diff --check` exits 0 with no output.

- [ ] **Step 6: Commit Task 6**

Run:

```powershell
git add docs/superpowers/specs/2026-05-26-history-relationship-reuse-design.md
git commit -m "docs: add bilingual history reuse spec"
```

---

### Task 7: Final Verification

**Files:**
- Verify all changed files from Tasks 1-6.

- [ ] **Step 1: Run history-focused tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_history_reuse_service.py tests\test_history_review_service.py -q
```

Expected: all history-focused tests PASS.

- [ ] **Step 2: Run API, service, and UI tests**

Run:

```powershell
uv --cache-dir .uv-cache run pytest tests\test_api_p0.py tests\test_services_p0_flow.py tests\test_streamlit_app.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 3: Run full test suite**

Run:

```powershell
uv --cache-dir .uv-cache run pytest -q
```

Expected: all tests PASS.

- [ ] **Step 4: Run ruff**

Run:

```powershell
uv --cache-dir .uv-cache run ruff check .
```

Expected: `All checks passed!`

- [ ] **Step 5: Inspect git status**

Run:

```powershell
git status --short --branch
```

Expected: only known unrelated local log files remain untracked unless the user asks to clean them.

- [ ] **Step 6: Commit final verification fixes if any files changed**

If verification required fixes, commit only those tracked implementation/doc files:

```powershell
git add src tests docs/superpowers/specs/2026-05-26-history-relationship-reuse-design.md
git commit -m "fix: stabilize history reuse flow"
```

If no files changed after verification, do not create an empty commit.

---

## Self-Review

- Spec coverage: data model semantics, history matching, review actions, API integration, graph/export filtering, name-first UI, tests, and bilingual spec follow-up are mapped to Tasks 1-6.
- Scope check: the plan does not add automatic replacement, a separate reconciliation table, external verification, two-hop graph, or React UI.
- Type consistency: public functions are named consistently across tests, API routing, and service implementation.
- Placeholder scan: no open-ended implementation placeholders are intentionally present.
