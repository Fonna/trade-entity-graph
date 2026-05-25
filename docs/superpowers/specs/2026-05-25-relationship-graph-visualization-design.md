# Relationship Graph Visualization Design

## Goal

在 Streamlit 工作台的“关系图谱”tab 中，为用户输入的中心企业 `entity_id` 提供一跳关系的可视化视图。该视图需要同时展示人工审核后的最终关系、待审核候选关系和订单证据边，并让用户能把候选关系 `claim_id` 带到现有“人工审核”tab 继续审核。

本设计优先支持当前 MVP 的人工审核闭环验证：用户可以看到候选关系在审核前如何出现在图谱中，也可以在审核后看到它作为最终关系进入图谱。

## Scope

Included:

- 在“关系图谱”tab 输入中心企业 ID 后渲染一跳 SVG 关系图。
- 在图中区分三类边：最终关系、待审核候选关系、订单证据边。
- 展示候选关系详情，包括 `claim_id`、关系类型、置信度、订单数和推荐理由。
- 支持将选中的候选关系 `claim_id` 写入 Streamlit `session_state`。
- “人工审核”tab 默认读取该 `claim_id`，但用户仍可手工覆盖。
- 复用现有 SQLite 表、服务层和 Streamlit 页面，不新增前端图谱依赖。
- 增加服务层和 UI 层测试，覆盖候选关系入图、审核跳转状态和 SVG 渲染入口。

Excluded:

- 图谱页内直接提交审核决策。
- 二跳展开、路径搜索、复杂图过滤器或自由拖拽布局。
- 引入 PyVis、streamlit-agraph、React、AntV G6、Cytoscape.js 或 Neo4j。
- 人工审核业务规则重构。
- 外部公开信息验证或企业关系自动判定。

## Chosen Approach

采用轻量内置 SVG 图谱方案。

Rationale:

- 当前项目已经依赖 `networkx`，可直接用 deterministic layout 生成节点坐标。
- SVG/HTML 可以通过 Streamlit 原生能力嵌入，不需要新增依赖或网络安装。
- MVP 重点是验证审核闭环，而不是构建完整交互式图数据库前端。
- 与现有 Streamlit 原型风格一致，后续如果需求稳定，可以替换为专业图谱组件。

Rejected alternatives:

- 表格增强方案开发最快，但不能满足“可视化页面展示关系”的目标。
- 新增专业图谱库交互更强，但会引入依赖、安装和维护成本，不适合当前 MVP 验证阶段。

## User Experience

### Graph Tab

用户在“关系图谱”tab 输入中心企业 `entity_id`，选择是否包含 rejected 最终关系，然后点击或自动触发查询。

页面主体分为两部分：

- 左侧：一跳关系 SVG 图谱。
- 右侧或下方：选中关系详情、候选关系列表和带到人工审核 tab 的入口。

图谱视觉编码：

- 中心企业节点使用深色高亮。
- 普通关联企业节点使用浅色圆形。
- 最终关系边使用实线，按状态或关系类型区分颜色。
- 待审核候选关系边使用橙色虚线，突出需要人工处理。
- 订单证据边使用灰色点线或细线，作为背景证据弱化展示。
- rejected 最终关系默认隐藏；勾选后以低饱和红色或灰色显示。

当用户选择候选关系时，详情区显示：

- `claim_id`
- 起点企业和终点企业
- `candidate_relation_type`
- `relation_status`
- `confidence_level`
- `confidence_score`
- `order_count`
- `total_teu`
- `recommendation_reason`

用户点击“带到人工审核 tab”后：

- `st.session_state["selected_claim_id"]` 被设置为当前 `claim_id`。
- 页面提示用户切换到“人工审核”tab 继续确认、否定或修改关系。

### Manual Review Tab

“人工审核”tab 保持现有审核入口，不在图谱页复制一套审核表单。

`claim_id` 输入框默认值读取：

```python
st.session_state.get("selected_claim_id", "")
```

用户仍可手动粘贴或覆盖 `claim_id`。提交审核后沿用现有 `decide_relationship()` 逻辑。

## Data Flow

### Current Inputs

现有服务已经提供：

- `get_ego_graph(center_entity_id, include_rejected=False)`：返回中心企业一跳节点、订单证据边和最终关系边。
- `list_relationship_claims_for_entity(entity_id)`：返回触达某个企业的候选关系。
- `get_relationship_detail(relationship_id)`：返回最终关系或候选关系详情。
- `decide_relationship(claim_id, ...)`：把候选关系审核写入最终关系和决策记录。

### View Model

新增或扩展图谱视图模型，将三类关系合并为前端渲染结构。

Nodes:

- 所有边的 `from_entity_id` 和 `to_entity_id` 去重。
- 中心企业即使没有边也要存在。
- 节点包含 `id`、`label`、`entity_type`、`tags`、`is_center`。

Edges:

- `curated_relationship` 边来自最终关系表。
- `relationship_claim` 边来自候选关系表，仅包含仍待审核的候选状态。
- `order_role_edge` 边来自订单证据表。

每条边保留统一字段：

- `id`
- `source`
- `target`
- `edge_type`
- `record_type`
- `relation_type`
- `status`
- `confidence_level`
- `confidence_score`
- `order_count`
- `total_teu`
- `label`

候选边的 `id` 必须等于 `claim_id`，便于带到人工审核 tab。

### Candidate Visibility

待审核候选关系进入图谱的条件：

- `from_entity_id = center_entity_id` 或 `to_entity_id = center_entity_id`
- `relation_status` 属于 `candidate` 或 `pending_verify`
- 已经产生对应 `curated_relationship` 的候选不再重复作为待审核候选显示

最终关系进入图谱的条件：

- `from_entity_id = center_entity_id` 或 `to_entity_id = center_entity_id`
- 默认排除 `relation_status = 'rejected'`
- 用户勾选 include rejected 后包含 rejected

订单证据边进入图谱的条件：

- `from_entity_id = center_entity_id` 或 `to_entity_id = center_entity_id`
- 作为证据背景展示，不参与审核跳转

## Layout

SVG 布局使用 `networkx.spring_layout()`，并设置固定 seed，保证同一组数据每次渲染位置稳定。

布局规则：

- 中心企业可固定或强制靠近画布中心。
- 一跳节点按布局算法分布在周围。
- 图谱视口大小适配 Streamlit 宽屏布局。
- 节点和边数量较少时仍保持可读间距。
- 图谱边数较多时优先保证最终关系和待审核候选关系可读，订单证据边视觉弱化。

SVG 渲染函数应是纯函数，输入图谱视图模型，输出 HTML/SVG 字符串，便于单元测试。

## Error Handling

- 中心企业 ID 为空时不查询，显示输入提示。
- 中心企业 ID 不存在时显示明确错误，不渲染误导性的空图。
- 中心企业存在但没有一跳关系时，显示中心节点和“暂无一跳关系”提示。
- 图谱存在候选关系但没有订单证据时，仍展示候选关系。
- 图谱存在订单证据但没有最终关系时，仍展示证据边和候选边。
- 候选关系被审核后，默认从待审核候选列表消失，并通过最终关系边显示审核结果。
- 如果 `session_state["selected_claim_id"]` 指向已不存在的候选关系，人工审核 tab 保留输入值但在提交时沿用现有错误提示。

## Testing

### Service Tests

Add tests around graph data behavior:

- 中心企业有候选关系时，图谱视图模型包含 `record_type = "relationship_claim"` 的边。
- 候选边保留 `claim_id`、`candidate_relation_type`、置信度和订单聚合字段。
- 已审核候选不再作为待审核候选边重复出现。
- 默认隐藏 rejected 最终关系，开启 include rejected 后显示。

### UI Tests

Add tests around Streamlit module structure:

- `render_graph_tab` 仍可调用。
- 新增 SVG 渲染函数可调用，并能输出 `<svg`。
- 新增候选选择/跳转 helper 能写入或读取 `selected_claim_id`。
- `render_review_tab` 的候选关系输入默认使用 `selected_claim_id`。

### Acceptance Flow

Using demo data:

1. 搜索一个中心企业 ID。
2. 图谱显示最终关系边、待审核候选边和订单证据边。
3. 选择一条候选关系，将 `claim_id` 带到“人工审核”tab。
4. 在“人工审核”tab 提交确认、否定或修改。
5. 回到图谱页后，候选关系不再作为待审核候选重复显示，并以最终关系结果呈现。

## Implementation Boundaries

This design intentionally keeps changes small:

- Service layer may add helper functions but should not rewrite existing review logic.
- UI layer may add rendering helpers but should not introduce a second review form.
- Database schema should remain unchanged.
- Existing API routes can remain unchanged unless a small response extension is needed for parity.
- Documentation and tests should describe the MVP limitation: one-hop graph only.

## Open Decisions Resolved

- Relationship scope: show final relationships, pending candidates, and order evidence edges.
- Review location: keep review submission in the existing “人工审核”tab.
- Visualization approach: use lightweight in-project SVG, no new dependency.
- Default rejected behavior: hide rejected relationships unless the user opts in.

## Spec Self-Review

- Placeholder scan: no incomplete markers remain.
- Consistency check: UX, data flow, and tests all use the same three edge categories.
- Scope check: this remains a single Streamlit MVP feature and does not include two-hop graph or direct graph-page review submission.
- Ambiguity check: candidate visibility, review handoff, rejected handling, and no-new-dependency constraints are explicit.
