# P1 Auxiliary Order Edges Design

## Goal

Complete the deferred P1 order-role auxiliary edges by generating `shipper_to_notify` and `consignee_to_notify` evidence edges from imported order evidence.

## Scope

Add two role-pair definitions to the existing order-role edge generator:

- `shipper_name` / `shipper` -> `notify_name` / `notify` as `shipper_to_notify`.
- `consignee_name` / `consignee` -> `notify_name` / `notify` as `consignee_to_notify`.

The implementation reuses existing validation: blank names, placeholders such as `SAME AS` and `TO ORDER`, YQN self roles, unknown entities, and same-entity pairs are skipped. Candidate aggregation, graph query, path query, evidence detail, API, and Streamlit reuse the existing `order_role_edge` table and require no additional behavior changes.

## Out of Scope

- No new tables.
- No new API endpoints.
- No changes to relationship-type inference; auxiliary edges remain evidence signals and aggregate into the existing candidate pipeline.
- No changes to structured supplemental evidence.

## Testing

Use TDD by first updating the relationship-service tests to expect the two P1 auxiliary edges for orders with a valid notify party, and to verify placeholders continue to be skipped. Then implement the role-pair additions and update any affected demo/API expectations.
