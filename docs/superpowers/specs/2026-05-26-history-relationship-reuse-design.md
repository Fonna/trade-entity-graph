# History Relationship Reuse And Conflict Review Design

## Goal

Add history relationship reuse to the MVP relationship review loop. After a new import generates
relationship candidates, the system should compare those candidates with the latest effective
manual review conclusions, mark candidates that match history, and flag candidates that conflict
with history for human review.

The feature must preserve the core product principle: historical review conclusions are reusable
assets, but they are not immutable. If a new import proves that a historical conclusion was wrong,
an operator can replace it with a new curated relationship while keeping the old conclusion
traceable as a deprecated version.

## Scope

Included:

- Persist history reuse status on `relationship_claim` instead of creating a separate reconciliation
  table.
- Mark new candidates as ordinary candidates, history matches, or history conflicts.
- Let human reviewers keep history, accept new evidence and supersede history, or mark a candidate
  for further verification.
- Preserve old curated relationships as `deprecated` when superseded.
- Link new relationships to old relationships with `supersedes_relationship_id`.
- Show business-facing entity names prominently in the manual review page.
- Keep `entity_id` and `claim_id` available as technical identifiers, but not as the primary review
  context.
- Add service and UI tests for matching, conflict detection, superseding, and name-first review
  display.

Excluded:

- No automatic replacement of historical conclusions.
- No new approval workflow or multi-step governance process.
- No independent reconciliation table in the first version.
- No external public-company verification.
- No two-hop graph or path-search expansion.
- No React rewrite or large UI redesign.

## Chosen Approach

Use `relationship_claim.relation_status` as the persistent state for history reuse. This keeps the
feature aligned with the existing flow:

```text
import -> order-role edges -> relationship_claim -> manual review -> curated_relationship
```

Rejected alternatives:

- UI-only hints are fast to build, but the result is not durable and cannot form a review queue.
- A separate `relationship_reconciliation` table is cleaner for a future data-governance module,
  but it is heavier than the current MVP needs.

## Data Model Semantics

No new table is required for the first version.

### Candidate Statuses

Extend the meaning of `relationship_claim.relation_status`:

- `candidate`: a normal new candidate with no effective historical match.
- `history_matched`: a candidate matched an effective historical conclusion and usually does not
  need repeat review.
- `history_conflict`: a candidate conflicts with an effective historical conclusion and needs
  manual review.
- `pending_verify`: a reviewer chose not to decide yet.

### Curated Relationship Statuses

Use these statuses on `curated_relationship.relation_status`:

- `verified`: current effective confirmed relationship.
- `manual_only`: current effective relationship created manually without a claim.
- `rejected`: current effective negative conclusion.
- `deprecated`: old historical conclusion replaced by a newer curated relationship.

The definition of a current effective relationship is:

```sql
relation_status IN ('verified', 'manual_only', 'rejected')
AND valid_to IS NULL
```

`deprecated` relationships do not participate in automatic reuse checks, default graph display, or
default exports. They remain visible through relationship history or detail views.

### Versioning Fields

When a reviewer accepts new evidence and replaces history:

- The old `curated_relationship` is updated to `relation_status = 'deprecated'`.
- The old relationship receives `valid_to = CURRENT_TIMESTAMP`.
- A new `curated_relationship` is inserted with the chosen current status and relation type.
- The new relationship writes `supersedes_relationship_id` with the old relationship ID.
- A `relationship_decision` row records `action_type = 'supersede'`.
- `audit_log` records both the old relationship deprecation and the new relationship creation.

## History Matching Rules

The first version uses deterministic, explainable rules. It never replaces history automatically.

### Match Scope

- Only current effective historical relationships participate.
- Deprecated relationships are ignored for automatic matching.
- Match the same entity pair by default with `from_entity_id + to_entity_id`.
- Symmetric relationship types can also match the reverse pair:
  - `same_entity`
  - `same_group`
  - `trading_partner`
- Directional relationship types use directed matching in the first version:
  - `subsidiary`
  - `factory_node`
  - `sales_center`
  - `logistics_service`

### Compatibility Rules

Candidate-to-history compatibility:

- `trading_partner_candidate` is compatible with `trading_partner`, `same_group`,
  `subsidiary`, `factory_node`, and `sales_center`.
- `factory_candidate` is compatible with `factory_node`, `subsidiary`, and `same_group`.
- `sales_center_candidate` is compatible with `sales_center`, `subsidiary`, and `same_group`.
- `same_group_candidate` is compatible with `same_group`, `subsidiary`, and `same_entity`.

The rule intentionally treats stronger historical relationships as compatible with weaker order
evidence. For example, if history says two entities are in the same group and a new order import
only suggests `trading_partner_candidate`, the candidate should be a history match, not a conflict.

### Status Outcomes

- Effective positive history plus compatible candidate: mark `history_matched`.
- Effective positive history plus incompatible candidate: mark `history_conflict`.
- Effective rejected history plus high or medium confidence positive candidate: mark
  `history_conflict`.
- Effective rejected history plus low confidence positive candidate: mark `history_matched`,
  meaning the historical negative conclusion still wins for now.
- No effective history: keep `candidate`.

The first version can use `confidence_level IN ('medium', 'high')` as the threshold for challenging
a rejected relationship. Order count and TEU can be shown in the explanation but do not need a
separate threshold unless tests reveal the confidence signal is too weak.

## Review Flow

History conflicts are reviewed in the existing manual review tab. There is no separate review page.

### Candidate Detail

When a reviewer opens a candidate, the page should show:

- Entity A canonical name.
- Entity B canonical name.
- New candidate relation type.
- Candidate confidence level and score.
- Order count, TEU, and recommendation reason.
- Matched historical relationship ID.
- Historical relation type and status.
- Historical reviewer, review time, and note when available.
- Conflict explanation in business language.

Technical IDs should be available in a collapsed or secondary block:

- `claim_id`
- `relationship_id`
- `from_entity_id`
- `to_entity_id`

### Review Actions

Support three actions for history-aware candidates:

- `keep_history`: keep the historical conclusion. The claim becomes or remains
  `history_matched`; no new curated relationship is created. A decision row records the reason.
- `supersede_history`: accept the new import conclusion. The old relationship becomes
  `deprecated`, a new relationship is created, and the new row points to the old row via
  `supersedes_relationship_id`.
- `mark_pending_verify`: leave history unchanged and set the claim to `pending_verify`.

The existing ordinary actions continue for normal candidates:

- `confirm`
- `reject`
- `modify`

## Service Design

Add a history reuse service near the relationship/review service layer.

Suggested functions:

- `apply_history_reuse_to_claims(run_id=None, db_path=None) -> dict[str, int]`
  - Finds candidates in the selected run or all runs.
  - Looks up current effective curated relationships for each candidate pair.
  - Updates `relationship_claim.relation_status`.
  - Writes an explanation into an existing text field if practical, or appends to
    `recommendation_reason` in the first version.
  - Returns counts for matched, conflicted, and unchanged candidates.
- `get_history_context_for_claim(claim_id, db_path=None) -> dict | None`
  - Returns the matched historical relationship and explanation for UI/API detail display.
- `keep_history_for_claim(claim_id, reason, operator, db_path=None) -> dict`
  - Marks a claim as `history_matched` and writes decision/audit rows.
- `supersede_history_with_claim(claim_id, old_relationship_id, relation_type, reason, operator,
  db_path=None) -> dict`
  - Deprecates the old relationship.
  - Creates the new relationship.
  - Writes decision and audit rows.
- `mark_claim_pending_verify(claim_id, reason, operator, db_path=None) -> dict`
  - Sets `relationship_claim.relation_status = 'pending_verify'`.
  - Writes decision/audit rows.

The import path should call history reuse after candidate aggregation:

```text
run_import(...)
generate_order_role_edges(...)
aggregate_relationship_claims(...)
apply_history_reuse_to_claims(run_id=...)
```

Existing callers that only aggregate candidates can still call `apply_history_reuse_to_claims`
explicitly.

## API Design

Keep API additions minimal:

- Relationship detail endpoints should include entity names and history context for candidates.
- The existing decision endpoint can either accept new `action_type` values or route to small helper
  functions internally:
  - `keep_history`
  - `supersede_history`
  - `mark_pending_verify`
- Import endpoint response can include a `history_reuse` summary:

```json
{
  "history_matched": 12,
  "history_conflict": 3,
  "unchanged": 18
}
```

No separate reconciliation API is required in the first version.

## UI Design

### Manual Review Page

The manual review page should be name-first:

- Primary display:
  - `主体 A：<canonical_name>`
  - `主体 B：<canonical_name>`
  - `新候选关系：<candidate_relation_type>`
  - `历史结论：<relation_type> / <relation_status>`
  - `冲突原因：<plain language explanation>`
- Secondary/collapsed display:
  - `claim_id`
  - `relationship_id`
  - `from_entity_id`
  - `to_entity_id`

Action labels should use business language:

- `沿用历史结论`
- `接受新证据，替代历史结论`
- `暂不判断，标记待验证`

Ordinary candidate review should also display the two entity names prominently. The reviewer should
not have to interpret raw entity IDs to make a decision.

### Graph Page

The graph page can continue to pass `claim_id` to the review tab through session state. The review
tab must immediately resolve the `claim_id` into the two entity names and relationship summary.

Graph display should include `history_conflict` candidates in the pending-candidate list. It can
show `history_matched` candidates as lower-priority rows or omit them from the default pending list
because they usually do not require action.

## Testing Strategy

Service tests:

- Effective positive history plus compatible candidate becomes `history_matched`.
- Effective rejected history plus high-confidence candidate becomes `history_conflict`.
- Effective rejected history plus low-confidence candidate becomes `history_matched`.
- Deprecated historical relationship is ignored by reuse matching.
- Symmetric relationship types match the reverse pair.
- Directional relationship types do not match the reverse pair in the first version.
- `keep_history` records a decision and does not create a new curated relationship.
- `supersede_history` marks the old relationship `deprecated`, sets `valid_to`, creates a new
  `verified` relationship, and writes `supersedes_relationship_id`.
- `mark_pending_verify` leaves the historical relationship unchanged.

API tests:

- Relationship detail for a candidate returns `from_name` and `to_name`.
- Relationship detail for a history conflict includes matched historical context.
- Import response includes history reuse counts when the endpoint runs aggregation.

UI tests:

- Manual review helper renders or formats the two entity names.
- Manual review helper exposes technical IDs only as secondary context.
- Graph-to-review handoff still uses `claim_id`, and the review tab resolves it to entity names.
- History conflict candidates are available for review.

## Migration Notes

SQLite schema already contains:

- `curated_relationship.supersedes_relationship_id`
- `curated_relationship.valid_from`
- `curated_relationship.valid_to`
- `relationship_decision.action_type`

The first version can avoid schema changes by using existing status and note fields. If later
explanations need to be structured, add fields such as:

- `relationship_claim.history_match_relationship_id`
- `relationship_claim.history_match_reason`

Those fields are not required for this initial implementation.

## Acceptance Criteria

- After importing and aggregating candidates, candidates that match effective history are marked
  `history_matched`.
- Candidates that challenge effective rejected history with medium/high confidence are marked
  `history_conflict`.
- A reviewer can choose to keep history without creating a duplicate final relationship.
- A reviewer can supersede history; the old relationship becomes `deprecated` and the new
  relationship points back to it.
- Default graph/export/reuse logic uses only current effective relationships.
- Manual review displays the two company names as the main decision context.
- Technical IDs remain available but are not the main review interface.
- All new service and UI tests pass.

## Open Decisions

None for the first version. If future business rules require more nuanced confidence thresholds,
the rule engine can be extended after observing real review data.
