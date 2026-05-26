# History Relationship Reuse And Conflict Review Design / 历史关系复用与冲突复核设计

> Format: each major section keeps the English design first, followed by a Chinese counterpart.
> 格式说明：每个主要章节先保留英文设计，再提供中文对照说明。

## Goal / 目标

Add history relationship reuse to the MVP relationship review loop. After a new import generates
relationship candidates, the system should compare those candidates with the latest effective
manual review conclusions, mark candidates that match history, and flag candidates that conflict
with history for human review.

The feature must preserve the core product principle: historical review conclusions are reusable
assets, but they are not immutable. If a new import proves that a historical conclusion was wrong,
an operator can replace it with a new curated relationship while keeping the old conclusion
traceable as a deprecated version.

为 MVP 关系复核闭环增加历史关系复用能力。新的导入任务生成关系候选后，系统应将这些候选与最新有效的人工复核结论进行比较：命中历史结论的候选标记为历史匹配，与历史结论冲突的候选进入人工复核。

该能力需要保留产品核心原则：历史复核结论是可复用资产，但不是不可变的真理。如果新的导入证据证明历史结论可能有误，操作员可以用新的人工确认关系替代它，同时将旧结论保留为可追溯的废弃版本。

## Scope / 范围

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

包含范围：

- 将历史复用状态持久化在 `relationship_claim` 上，不新增独立的 reconciliation 表。
- 将新候选标记为普通候选、历史匹配或历史冲突。
- 支持人工复核选择沿用历史、接受新证据并手动替代历史，或标记为待进一步验证。
- 历史结论被替代时，将旧的 curated relationship 保留为 `deprecated`。
- 通过 `supersedes_relationship_id` 建立新旧关系之间的替代链路。
- 在人工复核页面突出展示业务可读的主体名称。
- `entity_id` 和 `claim_id` 仍作为技术标识保留，但不作为主要复核上下文。
- 增加服务层和 UI 测试，覆盖匹配、冲突检测、替代历史以及名称优先的复核展示。

不包含范围：

- 不自动替换历史结论。
- 不新增审批流或多级治理流程。
- 首版不新增独立 reconciliation 表。
- 不接入外部上市公司或公开主体核验。
- 不扩展两跳图谱或路径搜索。
- 不进行 React 重写或大规模 UI 改版。

## Chosen Approach / 选定方案

Use `relationship_claim.relation_status` as the persistent state for history reuse. This keeps the
feature aligned with the existing flow:

```text
import -> order-role edges -> relationship_claim -> manual review -> curated_relationship
```

Rejected alternatives:

- UI-only hints are fast to build, but the result is not durable and cannot form a review queue.
- A separate `relationship_reconciliation` table is cleaner for a future data-governance module,
  but it is heavier than the current MVP needs.

使用 `relationship_claim.relation_status` 作为历史复用的持久状态字段，使该功能与现有流程保持一致：

```text
import -> order-role edges -> relationship_claim -> manual review -> curated_relationship
```

被拒绝的替代方案：

- 只在 UI 上提示实现较快，但结果不可持久化，也无法形成稳定的复核队列。
- 独立的 `relationship_reconciliation` 表更适合未来的数据治理模块，但对当前 MVP 来说过重。

## Data Model Semantics / 数据模型语义

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

首版不需要新增表。

### 候选状态

扩展 `relationship_claim.relation_status` 的含义：

- `candidate`：普通新候选，没有匹配到有效历史结论。
- `history_matched`：候选与有效历史结论匹配，通常不需要重复复核。
- `history_conflict`：候选与有效历史结论冲突，需要人工复核。
- `pending_verify`：复核人员暂不作结论，标记为待验证。

### 人工确认关系状态

`curated_relationship.relation_status` 使用以下状态：

- `verified`：当前有效的正向确认关系。
- `manual_only`：未来源于 claim、由人工直接创建的当前有效关系。
- `rejected`：当前有效的负向结论。
- `deprecated`：已被新关系替代的旧历史结论。

当前有效关系定义为：

```sql
relation_status IN ('verified', 'manual_only', 'rejected')
AND valid_to IS NULL
```

`deprecated` 关系不参与自动历史复用检查、默认图谱展示或默认导出，但仍可在关系历史或详情视图中查看。当前有效图谱和导出逻辑应同时满足 `valid_to IS NULL` 且状态未废弃。

### 版本字段

当复核人员接受新证据并替代历史时：

- 旧 `curated_relationship` 更新为 `relation_status = 'deprecated'`。
- 旧关系写入 `valid_to = CURRENT_TIMESTAMP`。
- 插入新的 `curated_relationship`，使用复核人员选择的当前状态和关系类型。
- 新关系的 `supersedes_relationship_id` 写入旧关系 ID。
- `relationship_decision` 记录 `action_type = 'supersede'`。
- `audit_log` 同时记录旧关系废弃和新关系创建。

## History Matching Rules / 历史匹配规则

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

首版使用确定、可解释的规则，且永远不自动替换历史结论。

### 匹配范围

- 只有当前有效的历史关系参与匹配。
- `deprecated` 关系在自动匹配中被忽略。
- 默认按同一主体对匹配，即 `from_entity_id + to_entity_id`。
- 对称关系类型也可以反向匹配：
  - `same_entity`
  - `same_group`
  - `trading_partner`
- 有方向关系类型首版使用有向匹配：
  - `subsidiary`
  - `factory_node`
  - `sales_center`
  - `logistics_service`

### 兼容规则

候选与历史关系的兼容性：

- `trading_partner_candidate` 兼容 `trading_partner`、`same_group`、`subsidiary`、`factory_node` 和 `sales_center`。
- `factory_candidate` 兼容 `factory_node`、`subsidiary` 和 `same_group`。
- `sales_center_candidate` 兼容 `sales_center`、`subsidiary` 和 `same_group`。
- `same_group_candidate` 兼容 `same_group`、`subsidiary` 和 `same_entity`。

该规则有意将更强的历史关系视为兼容较弱的订单证据。例如，历史结论认为两个主体属于同一集团，而新的订单导入只提示 `trading_partner_candidate`，则该候选应标记为历史匹配，而不是冲突。

### 状态结果

- 有效正向历史 + 兼容候选：标记为 `history_matched`。
- 有效正向历史 + 不兼容候选：标记为 `history_conflict`。
- 有效拒绝历史 + 高或中置信度正向候选：标记为 `history_conflict`。
- 有效拒绝历史 + 低置信度正向候选：标记为 `history_matched`，表示当前仍沿用历史负向结论。
- 没有有效历史：保持 `candidate`。

首版可使用 `confidence_level IN ('medium', 'high')` 作为挑战被拒绝关系的阈值。订单数和 TEU 可展示在解释中，但除非测试表明置信度信号不足，否则不单独设置阈值。

## Review Flow / 复核流程

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

Review mutations are manual and guarded. Reuse reruns may update claim classification and context,
but they must not overwrite existing review decisions or claim history/review artifacts.

历史冲突在现有人工复核页签中处理，不新增独立复核页面。

### 候选详情

复核人员打开候选时，页面应展示：

- 主体 A 标准名称。
- 主体 B 标准名称。
- 新候选关系类型。
- 候选置信等级和分数。
- 订单数、TEU 和推荐原因。
- 命中的历史关系 ID。
- 历史关系类型和状态。
- 如有，展示历史复核人员、复核时间和备注。
- 用业务语言说明冲突原因。

技术 ID 应放在折叠区或次要区块中：

- `claim_id`
- `relationship_id`
- `from_entity_id`
- `to_entity_id`

### 复核动作

历史感知候选支持三个动作：

- `keep_history`：沿用历史结论。claim 变为或保持 `history_matched`，不创建新的 curated relationship，并记录决策原因。
- `supersede_history`：接受新的导入结论。旧关系变为 `deprecated`，创建新关系，并通过 `supersedes_relationship_id` 指向旧关系。
- `mark_pending_verify`：保持历史不变，将 claim 设置为 `pending_verify`。

普通候选继续使用已有动作：

- `confirm`
- `reject`
- `modify`

复核写操作必须由人工触发并受保护。历史复用重跑可以更新 claim 分类和上下文，但不得覆盖已有的复核决策、claim 历史或复核相关记录。

## Service Design / 服务设计

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

在关系/复核服务层附近增加历史复用服务。

建议函数：

- `apply_history_reuse_to_claims(run_id=None, db_path=None) -> dict[str, int]`
  - 查找指定 run 或全部 run 中的候选。
  - 为每个候选主体对查找当前有效的 curated relationship。
  - 更新 `relationship_claim.relation_status`。
  - 在可行时将解释写入现有文本字段；首版也可追加到 `recommendation_reason`。
  - 返回匹配、冲突和未变化的数量。
- `get_history_context_for_claim(claim_id, db_path=None) -> dict | None`
  - 返回命中的历史关系和解释，用于 UI/API 详情展示。
- `keep_history_for_claim(claim_id, reason, operator, db_path=None) -> dict`
  - 将 claim 标记为 `history_matched`，并写入 decision/audit 记录。
- `supersede_history_with_claim(claim_id, old_relationship_id, relation_type, reason, operator, db_path=None) -> dict`
  - 废弃旧关系。
  - 创建新关系。
  - 写入 decision 和 audit 记录。
- `mark_claim_pending_verify(claim_id, reason, operator, db_path=None) -> dict`
  - 设置 `relationship_claim.relation_status = 'pending_verify'`。
  - 写入 decision/audit 记录。

导入路径应在候选聚合后调用历史复用：

```text
run_import(...)
generate_order_role_edges(...)
aggregate_relationship_claims(...)
apply_history_reuse_to_claims(run_id=...)
```

仅执行候选聚合的现有调用方仍可显式调用 `apply_history_reuse_to_claims`。如果某次导入没有生成新的边或候选，已有导入关系 claim 不应因此被删除或覆盖。

## API Design / API 设计

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

API 增量保持最小：

- 关系详情接口应为候选返回主体名称和历史上下文。
- 现有决策接口可以直接接受新的 `action_type`，也可以在内部路由到小的 helper 函数：
  - `keep_history`
  - `supersede_history`
  - `mark_pending_verify`
- 导入接口响应可包含 `history_reuse` 汇总：

```json
{
  "history_matched": 12,
  "history_conflict": 3,
  "unchanged": 18
}
```

首版不需要独立 reconciliation API。

## UI Design / UI 设计

### Manual Review Page

The manual review page should be name-first:

- Primary display:
  - `Entity A: <canonical_name>`
  - `Entity B: <canonical_name>`
  - `New candidate relationship: <candidate_relation_type>`
  - `Historical conclusion: <relation_type> / <relation_status>`
  - `Conflict reason: <plain language explanation>`
- Secondary/collapsed display:
  - `claim_id`
  - `relationship_id`
  - `from_entity_id`
  - `to_entity_id`

Action labels should use business language:

- `Keep historical conclusion`
- `Accept new evidence and supersede historical conclusion`
- `Defer decision and mark as pending verification`

Ordinary candidate review should also display the two entity names prominently. The reviewer should
not have to interpret raw entity IDs to make a decision.

### Graph Page

The graph page can continue to pass `claim_id` to the review tab through session state. The review
tab must immediately resolve the `claim_id` into the two entity names and relationship summary.

Graph display should include `history_conflict` candidates in the pending-candidate list. It can
show `history_matched` candidates as lower-priority rows or omit them from the default pending list
because they usually do not require action.

### 人工复核页面

人工复核页面应采用名称优先的展示方式：

- 主要展示：
  - `主体 A：<canonical_name>`
  - `主体 B：<canonical_name>`
  - `新候选关系：<candidate_relation_type>`
  - `历史结论：<relation_type> / <relation_status>`
  - `冲突原因：<plain language explanation>`
- 次要/折叠展示：
  - `claim_id`
  - `relationship_id`
  - `from_entity_id`
  - `to_entity_id`

操作按钮应使用业务语言：

- `沿用历史结论`
- `接受新证据，替代历史结论`
- `暂不判断，标记待验证`

普通候选复核也应突出展示两个主体名称。复核人员不应依赖原始 entity ID 来做业务判断。

### 图谱页面

图谱页面可以继续通过 session state 将 `claim_id` 传递给复核页签。复核页签必须立即将 `claim_id` 解析为两个主体名称和关系摘要。

图谱展示应将 `history_conflict` 候选纳入待处理候选列表。`history_matched` 候选可作为低优先级行展示，也可从默认待处理列表中省略，因为它们通常无需人工处理。

## Testing Strategy / 测试策略

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
- Reuse reruns do not overwrite claim history or existing review artifacts.
- Imported relationship claims are preserved when no generated edges exist.

API tests:

- Relationship detail for a candidate returns `from_name` and `to_name`.
- Relationship detail for a history conflict includes matched historical context.
- Import response includes history reuse counts when the endpoint runs aggregation.

UI tests:

- Manual review helper renders or formats the two entity names.
- Manual review helper exposes technical IDs only as secondary context.
- Graph-to-review handoff still uses `claim_id`, and the review tab resolves it to entity names.
- History conflict candidates are available for review.

服务测试：

- 有效正向历史 + 兼容候选应变为 `history_matched`。
- 有效拒绝历史 + 高置信度候选应变为 `history_conflict`。
- 有效拒绝历史 + 低置信度候选应变为 `history_matched`。
- `deprecated` 历史关系应被复用匹配忽略。
- 对称关系类型应支持反向主体对匹配。
- 首版有方向关系类型不做反向匹配。
- `keep_history` 应记录决策，且不创建新的 curated relationship。
- `supersede_history` 应将旧关系标记为 `deprecated`、设置 `valid_to`、创建新的 `verified` 关系，并写入 `supersedes_relationship_id`。
- `mark_pending_verify` 应保持历史关系不变。
- 历史复用重跑不得覆盖 claim 历史或已有复核记录。
- 当没有生成边时，已导入的 relationship claim 应被保留。

API 测试：

- 候选关系详情返回 `from_name` 和 `to_name`。
- 历史冲突的关系详情包含命中的历史上下文。
- 当导入接口执行聚合时，响应包含历史复用计数。

UI 测试：

- 人工复核 helper 渲染或格式化两个主体名称。
- 人工复核 helper 仅将技术 ID 作为次要上下文展示。
- 图谱到复核的跳转仍使用 `claim_id`，复核页签将其解析为主体名称。
- 历史冲突候选可进入复核。

## Migration Notes / 迁移说明

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

SQLite schema 已包含：

- `curated_relationship.supersedes_relationship_id`
- `curated_relationship.valid_from`
- `curated_relationship.valid_to`
- `relationship_decision.action_type`

首版可以通过复用现有状态和备注字段避免 schema 变更。如果后续需要结构化解释，可再增加字段，例如：

- `relationship_claim.history_match_relationship_id`
- `relationship_claim.history_match_reason`

这些字段不是首版实现的必要条件。

## Acceptance Criteria / 验收标准

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
- Review mutations are manual and guarded; reuse reruns do not overwrite claim history or review
  artifacts.
- Imported relationship claims are preserved when no generated edges exist.
- All new service and UI tests pass.

- 导入并聚合候选后，与有效历史匹配的候选被标记为 `history_matched`。
- 以中/高置信度挑战有效拒绝历史的候选被标记为 `history_conflict`。
- 复核人员可以选择沿用历史，且不会创建重复的最终关系。
- 复核人员可以手动替代历史；旧关系变为 `deprecated`，新关系回指旧关系。
- 默认图谱、导出和复用逻辑仅使用当前有效关系。
- 人工复核以两个公司名称作为主要决策上下文。
- 技术 ID 仍可查看，但不是主要复核界面。
- 复核写操作必须人工触发并受保护；历史复用重跑不得覆盖 claim 历史或复核记录。
- 当没有生成边时，已导入的 relationship claim 被保留。
- 新增服务层和 UI 测试全部通过。

## Open Decisions / 待定事项

None for the first version. If future business rules require more nuanced confidence thresholds,
the rule engine can be extended after observing real review data.

首版无待定事项。如果未来业务规则需要更细的置信度阈值，可在观察真实复核数据后扩展规则引擎。
