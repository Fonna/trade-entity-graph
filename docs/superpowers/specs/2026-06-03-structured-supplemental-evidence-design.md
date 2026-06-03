# Structured Supplemental Evidence Design

## Goal

Add structured supplemental evidence for relationship candidates and curated relationships, without implementing P1 auxiliary order-role edges in this iteration.

## Scope

This change lets users record non-order evidence such as public web findings, sales feedback, business documents, and manual notes. Evidence can be attached to either a `relationship_claim` or a `curated_relationship`. When a candidate is reviewed into a curated relationship, optional supplemental evidence can be carried forward while retaining the original `claim_id` for traceability.

Out of scope:

- Do not add `shipper_to_notify` or `consignee_to_notify` order-role edges.
- Do not change graph edge generation or candidate aggregation logic.
- Do not backfill historical plan checkboxes.
- Do not introduce file upload or attachment binary storage.

## Data Model

Create `relationship_external_evidence`:

- `external_evidence_id` primary key.
- `relationship_id` nullable reference to `curated_relationship`.
- `claim_id` nullable reference to `relationship_claim`.
- `evidence_type` required, e.g. `public_web`, `sales_feedback`, `business_document`, `manual_note`.
- `source_title`, `source_url`, `source_name`, `evidence_summary`, `evidence_date`, `confidence_level`.
- `created_by` required and `created_at` default timestamp.

At least one of `relationship_id` or `claim_id` must be set at service level. SQLite CHECK constraints are intentionally avoided for legacy migration simplicity; service validation enforces the rule.

## Services and API

Add service helpers in `relationship_service.py`:

- `create_external_evidence(target_id, evidence, db_path=None)` resolves `target_id` through `get_relationship_detail()` and inserts the evidence with the appropriate relationship or claim binding.
- `list_external_evidence(target_id, db_path=None)` returns evidence attached directly to the target; for curated relationships created from a claim, it also returns evidence attached to the source claim.
- `get_relationship_evidence()` returns order-role evidence rows and supplemental evidence rows, each tagged with `evidence_record_type`.

Add API support in `relationships.py`:

- `POST /relationships/{relationship_id}/external-evidence` creates one supplemental evidence record.
- `DecisionRequest` and `ManualRelationshipRequest` accept optional `external_evidence`.
- Review/manual-create endpoints pass optional evidence to the service layer.

## UI

Update Streamlit to:

- Render relationship evidence as two sections: order evidence and supplemental evidence.
- Add optional supplemental evidence fields to ordinary review, history review, pending verify, and manual-create forms.
- Keep all fields optional except summary when a user chooses to add supplemental evidence. Empty evidence forms should not create rows.

## Documentation

Update current project documentation:

- `README.md` and `README.en.md`: current status, structured supplemental evidence, fresh verification count.
- `docs/task-breakdown.md`: mark `CUR-05` as implemented and update current status.
- `docs/technical-plan.md`: add the new evidence table/API/UI behavior and update stale M8 status.
- `docs/local-relationship-reuse-guide.md`: document that external agents should include evidence in import notes today and should use the API/UI for structured supplemental evidence; they must not write the table directly.

## Testing

Use TDD:

1. Add schema tests for the new table and legacy initialization.
2. Add service tests for creating evidence on claims and curated relationships, listing claim-carried evidence after review, and combined evidence output tags.
3. Add API tests for the new endpoint and optional review evidence.
4. Add Streamlit tests for helper rendering and optional payload creation.
5. Run focused tests, then full pytest and ruff.
