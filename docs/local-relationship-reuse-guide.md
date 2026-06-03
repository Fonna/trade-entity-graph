# 本机企业主体关系复用与外部 Agent 导入指南
## 2026-06-03 Structured Supplemental Evidence Access

This project supports structured supplemental evidence for relationship candidates and curated relationships through `relationship_external_evidence`. External agents must not write this table directly; generate importable candidate/confirmed relationship files first, then use the Streamlit UI or FastAPI to append structured evidence.

API example:

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/relationships/CLM_xxx/external-evidence" `
  -ContentType "application/json" `
  -Body '{
    "evidence_type":"public_web",
    "source_title":"Company profile",
    "source_url":"https://example.com/company",
    "source_name":"public registry",
    "evidence_summary":"Public information supports the relationship",
    "evidence_date":"2026-06-03",
    "confidence_level":"medium",
    "created_by":"external_agent"
  }'
```

If an external agent only outputs CSV/Excel import packages, put evidence summaries in `recommendation_reason` or `decision_note`, then append structured supplemental evidence through this project API/UI after import.

> 最新核对日期：2026-06-03
> 核对依据：`src/trade_entity_graph/importers/field_mappings/default.json`、`src/trade_entity_graph/importers/pipeline.py`、`src/trade_entity_graph/importers/relationship_loader.py`、`src/trade_entity_graph/api/routers/imports.py`。

本文档面向同一台电脑上的其他项目和 Agent。用途有两类：

1. 只读复用 `trade-entity-graph` 已沉淀的企业主体、别名和已确认关系。
2. 自动整理并导出 CSV/Excel 文件，让本项目可以通过数据导入页或 `/imports/run` API 直接导入。

如果其他项目的 Agent 只允许读取一个使用指南，应优先读取本文档。

## 1. 使用边界

推荐方式：其他项目只读访问本项目 SQLite 数据库，或生成导入文件后交给本项目导入流程写入。不要绕过导入、审核、审计和原始文件归档机制直接改表。

适合场景：

- 另一个本地 Python 项目需要判断两家企业是否已确认同主体、同集团或存在其他已确认关系。
- 批量处理订单、客户、收发货人、通知人时，需要复用历史人工确认结论。
- 外部 Agent 已经完成企业清洗、订单整理、候选关系或已确认关系整理，需要导出本项目可导入的数据文件。

不要做的事情：

- 不要直接写入 `curated_relationship`、`relationship_decision`、`entity`、`entity_alias`、`audit_log`。
- 不要把订单共现、收发货角色共现直接当作最终企业关系。
- 不要默认把 `A-B same_group`、`B-C same_group` 自动推导成 `A-C same_group`，除非业务明确允许集团连通推断。
- 不要把 `same_entity` 和 `same_group` 混用；前者用于同一主体归并，后者用于集团识别。

## 2. 本项目地址与数据库位置

项目目录：

```text
D:\Github\trade-entity-graph
```

默认 SQLite 数据库：

```text
D:\Github\trade-entity-graph\data\processed\trade_entity_graph.db
```

如果本项目运行时配置过 `TEG_DATABASE_PATH`，应以该环境变量指向的数据库为准。建议外部项目用只读环境变量保存路径：

```powershell
$env:TEG_RELATIONSHIP_DB="D:\Github\trade-entity-graph\data\processed\trade_entity_graph.db"
```

## 3. 外部 Agent 应该导出哪些文件

本项目当前导入流程支持 4 类输入文件，均可使用 `.csv`、`.xlsx`、`.xlsm`、`.xls`。Excel 默认读取第一个 sheet；如果希望最稳妥，建议外部 Agent 生成 UTF-8 CSV。

| 导入角色 | API/代码字段 | Streamlit 输入框 | 写入位置 | 外部 Agent 何时生成 |
| --- | --- | --- | --- | --- |
| 企业主体 | `entities_path` | 企业清洗结果文件路径 | `entity`、`entity_alias`、`import_entity` | 有新增企业、别名、清洗名时 |
| 订单证据 | `orders_path` | 订单明细文件路径 | `order_evidence`，后续可生成订单角色边和候选关系 | 有订单/提单/角色证据时 |
| 关系候选 | `relationships_path` | 已有关系候选文件路径 | `relationship_claim` | 只是线索，仍需人工审核时 |
| 已确认关系 | `confirmed_relationships_path` | 已确认关系文件路径（直接进入最终关系） | `curated_relationship`、`relationship_decision`、`audit_log` | 已由业务或人工确认，可直接沉淀为最终关系时 |

重要顺序：同一次导入中，系统会先导入 `entities_path`，再导入 `orders_path`、`relationships_path`、`confirmed_relationships_path`。因此，如果关系文件使用企业名称而不是 `entity_id`，可以把对应企业文件和关系文件放在同一次导入中。

## 4. 推荐数据包结构

外部 Agent 可以导出到任意目录，但推荐统一命名，便于人工检查和导入：

```text
agent_export_<batch_id>/
  entities.csv
  orders.csv
  relationship_candidates.csv
  confirmed_relationships.csv
  README.md              # 可选：说明数据来源、整理规则、负责人、时间
```

最小可导入数据包可以只有其中一个文件，但本项目导入时至少需要提供一个路径。

## 5. 企业主体文件格式：`entities.csv`

必填字段：`canonical_name`。其他字段可选。

推荐列：

```csv
canonical_name,original_name,clean_name,alias_name,country,entity_type
ACME TRADING,Acme Trading Ltd,ACME TRADING LTD,ACME,US,customer
BETA FACTORY,Beta Factory Inc,BETA FACTORY INC,,CN,factory
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `canonical_name` | 是 | 企业标准名；导入时会标准化后写入主体库 |
| `original_name` | 否 | 原始名称，会写入别名，`alias_type=original_name` |
| `clean_name` | 否 | 清洗后名称，会写入别名，`alias_type=clean_name` |
| `alias_name` | 否 | 其他别名，会写入别名，`alias_type=alias` |
| `country` | 否 | 国家/地区 |
| `entity_type` | 否 | 主体类型，例如 `customer`、`factory`、`buyer`、`supplier` |

可识别列名别名：

- `canonical_name`：`canonical_name`、`standard_name`、`标准名`、`企业标准名`
- `original_name`：`original_name`、`raw_name`、`原始名`、`原始企业名`
- `clean_name`：`clean_name`、`cleaned_name`、`清洗名`、`清洗后名称`
- `alias_name`：`alias_name`、`alias`、`别名`、`企业别名`
- `country`：`country`、`国家`、`国家地区`
- `entity_type`：`entity_type`、`主体类型`、`企业类型`

## 6. 订单证据文件格式：`orders.csv`

必填字段：`order_id`。其他字段可选。`teu` 如果填写，必须是数字。

推荐列：

```csv
order_id,customer_name,shipper_name,consignee_name,notify_name,teu,product_name,function_category,destination_country,destination_port,order_date
SO-1,ACME TRADING,BETA FACTORY,OMEGA BUYER,OMEGA BUYER,3.5,Widget,Parts,MX,Manzanillo,2026-06-01
SO-2,ACME TRADING,BETA FACTORY,OMEGA BUYER,SAME AS,4.0,Widget,Parts,MX,Manzanillo,2026-06-02
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `order_id` | 是 | 订单号/业务编号/提单号 |
| `customer_name` | 否 | 下单客户 |
| `shipper_name` | 否 | 发货人 |
| `consignee_name` | 否 | 收货人 |
| `notify_name` | 否 | 通知人 |
| `teu` | 否 | 箱量；必须可转成数字 |
| `product_name` | 否 | 产品/品名 |
| `function_category` | 否 | 产品功能分类 |
| `destination_country` | 否 | 目的国 |
| `destination_port` | 否 | 目的港 |
| `order_date` | 否 | 订单日期/出运日期 |

可识别列名别名：

- `order_id`：`order_id`、`订单号`、`业务编号`、`提单号`、`so_no`
- `customer_name`：`customer_name`、`客户名称`、`下单客户`、`Booking Customer`、`customer`
- `shipper_name`：`shipper_name`、`发货人`、`Shipper`、`shipper`
- `consignee_name`：`consignee_name`、`收货人`、`Consignee`、`consignee`
- `notify_name`：`notify_name`、`通知人`、`Notify Party`、`notify`
- `teu`：`teu`、`TEU`、`箱量`、`箱量TEU`
- `product_name`：`product_name`、`产品名称`、`货品名称`、`品名`、`产品`
- `function_category`：`function_category`、`功能分类`、`产品功能`
- `destination_country`：`destination_country`、`目的国`、`目的国家`
- `destination_port`：`destination_port`、`目的港`、`目的港口`
- `order_date`：`order_date`、`订单日期`、`出运日期`

## 7. 关系候选文件格式：`relationship_candidates.csv`

关系候选写入 `relationship_claim`，只是待审核线索，不会直接成为最终关系。

推荐列：

```csv
from_entity_name,to_entity_name,candidate_relation_type,confidence_level,confidence_score,order_count,total_teu,recommendation_reason
ACME TRADING,BETA FACTORY,trading_partner_candidate,medium,0.72,3,8.5,多票订单中反复出现客户-发货人工厂组合
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `from_entity_id` / `from_entity_name` | 二选一 | 起点主体。优先用 ID；没有 ID 时用名称匹配 `entity`/`entity_alias` |
| `to_entity_id` / `to_entity_name` | 二选一 | 终点主体。优先用 ID；没有 ID 时用名称匹配 `entity`/`entity_alias` |
| `candidate_relation_type` | 否 | 默认 `trading_partner_candidate` |
| `confidence_level` | 否 | 置信等级，如 `high`、`medium`、`low` |
| `confidence_score` | 否 | 数字；空值允许 |
| `order_count` | 否 | 数字；空值默认 0 |
| `total_teu` | 否 | 数字；空值默认 0 |
| `recommendation_reason` | 否 | 推荐理由 |

可识别列名别名：

- `from_entity_id`：`from_entity_id`、`source_entity_id`、`起点主体ID`
- `to_entity_id`：`to_entity_id`、`target_entity_id`、`终点主体ID`
- `from_entity_name`：`from_entity_name`、`主体A`、`企业A`、`起点企业`
- `to_entity_name`：`to_entity_name`、`主体B`、`企业B`、`终点企业`
- `candidate_relation_type`：`candidate_relation_type`、`关系类型`、`候选关系类型`
- `confidence_level`：`confidence_level`、`置信度等级`、`置信等级`
- `confidence_score`：`confidence_score`、`置信度分数`、`score`
- `order_count`：`order_count`、`订单数`
- `total_teu`：`total_teu`、`总TEU`、`teu_total`
- `recommendation_reason`：`recommendation_reason`、`推荐理由`、`reason`

## 8. 已确认关系文件格式：`confirmed_relationships.csv`

已确认关系会直接写入最终关系表，并同步写入决策记录和审计日志。只有在外部 Agent 的结论已经经过业务确认、人工确认或可解释证据确认时才使用这个入口。

推荐列：

```csv
from_entity_name,to_entity_name,relation_type,relation_status,confidence_level,confidence_score,source_type,decision_note
ACME TRADING,BETA FACTORY,same_group,verified,high,0.92,imported_confirmed,业务已确认两家公司属于同一集团
BETA FACTORY,OMEGA BUYER,trading_partner,verified,medium,0.75,imported_confirmed,历史订单和人工复核确认贸易伙伴关系
```

字段说明：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `from_entity_id` / `from_entity_name` | 二选一 | 起点主体。优先用 ID；没有 ID 时用名称匹配 `entity`/`entity_alias` |
| `to_entity_id` / `to_entity_name` | 二选一 | 终点主体。优先用 ID；没有 ID 时用名称匹配 `entity`/`entity_alias` |
| `relation_type` | 是 | 最终关系类型 |
| `relation_status` | 否 | 默认 `verified` |
| `confidence_level` | 否 | 置信等级 |
| `confidence_score` | 否 | 数字；空值允许 |
| `source_type` | 否 | 默认 `imported_confirmed` |
| `decision_note` | 否 | 默认 `imported confirmed relationship`；建议必须填写清楚证据和确认来源 |

可识别列名别名：

- `from_entity_id`：`from_entity_id`、`source_entity_id`、`from_id`、`起点主体ID`
- `to_entity_id`：`to_entity_id`、`target_entity_id`、`to_id`、`终点主体ID`
- `from_entity_name`：`from_entity_name`、`from_name`、`source_entity_name`、`主体A`、`企业A`、`起点企业`
- `to_entity_name`：`to_entity_name`、`to_name`、`target_entity_name`、`主体B`、`企业B`、`终点企业`
- `relation_type`：`relation_type`、`relationship_type`、`confirmed_relation_type`、`关系类型`、`最终关系类型`
- `relation_status`：`relation_status`、`status`、`关系状态`
- `confidence_level`：`confidence_level`、`confidence`、`置信度等级`、`置信等级`
- `confidence_score`：`confidence_score`、`score`、`置信度分数`
- `source_type`：`source_type`、`来源类型`
- `decision_note`：`decision_note`、`reason`、`note`、`确认理由`、`备注`

## 9. 关系类型与状态建议

外部 Agent 输出关系时，应优先使用以下 `relation_type`：

| relation_type | 含义 | 使用建议 |
| --- | --- | --- |
| `same_entity` | 同一企业主体 | 可用于客户去重、订单归并、企业名归一 |
| `same_group` | 同集团 | 可用于集团客户识别和机会分析；不要合并成同一主体 |
| `subsidiary` | 子公司或海外公司 | 注意方向，建议在 `decision_note` 写清母子关系判断依据 |
| `factory_node` | 海外工厂或生产节点 | 用于海外节点识别和机会分析 |
| `sales_center` | 销售中心 | 用于销售网络识别 |
| `trading_partner` | 普通贸易伙伴 | 只表示业务往来，不代表同集团 |
| `logistics_service` | 物流、货代、仓储、清关等服务关系 | 通常不作为集团或主体关系 |
| `rejected_relation` | 已否定关系 | 表示历史审核明确否定，不要自动推断成正向关系 |

推荐 `relation_status`：

| relation_status | 含义 | 是否可作为确认结论 |
| --- | --- | --- |
| `verified` | 已确认关系 | 是 |
| `manual_only` | 人工新增关系，可能暂无订单证据 | 是 |
| `rejected` | 已否定关系 | 是，但表示反向结论 |
| `pending_verify` | 待进一步验证 | 否，只能提示 |
| `conflict` | 证据冲突 | 否，需要人工处理 |
| `deprecated` | 历史关系，已被替代 | 否 |
| `candidate` | 系统候选 | 否 |

## 10. 导入方式

### 10.1 通过 Streamlit 页面导入

启动本项目工作台：

```powershell
cd D:\Github\trade-entity-graph
uv --cache-dir .uv-cache run python scripts\run_ui.py
```

打开数据导入页，填写对应文件路径：

- 企业清洗结果文件路径：`entities.csv`
- 订单明细文件路径：`orders.csv`
- 已有关系候选文件路径：`relationship_candidates.csv`
- 已确认关系文件路径（直接进入最终关系）：`confirmed_relationships.csv`

### 10.2 通过 FastAPI 导入

启动 API：

```powershell
cd D:\Github\trade-entity-graph
uv --cache-dir .uv-cache run python scripts\run_api.py
```

导入示例：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/imports/run" `
  -ContentType "application/json" `
  -Body '{
    "entities_path":"D:\\path\\agent_export_001\\entities.csv",
    "orders_path":"D:\\path\\agent_export_001\\orders.csv",
    "relationships_path":"D:\\path\\agent_export_001\\relationship_candidates.csv",
    "confirmed_relationships_path":"D:\\path\\agent_export_001\\confirmed_relationships.csv",
    "imported_by":"external_agent",
    "generate_edges":true,
    "aggregate_claims":true
  }'
```

说明：

- `generate_edges=true` 时，导入订单后会生成订单角色边。
- `aggregate_claims=true` 且生成了订单角色边时，会聚合生成关系候选，并尝试复用历史确认关系。
- `/imports/run` 接收的是本机文件路径，不是文件上传接口。
- 导入时会复制源文件到 `data/raw/imports/<run_id>/`，并记录 SHA256 和文件角色。

### 10.3 导入前查重与导入后质量检查

导入前可检查源文件是否与历史导入重复：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/imports/duplicate-check" `
  -ContentType "application/json" `
  -Body '{"confirmed_relationships_path":"D:\\path\\confirmed_relationships.csv"}'
```

导入后可查询质量结果：

```text
GET http://127.0.0.1:8000/imports
GET http://127.0.0.1:8000/imports/{run_id}
GET http://127.0.0.1:8000/imports/{run_id}/errors
GET http://127.0.0.1:8000/imports/{run_id}/errors/export
GET http://127.0.0.1:8000/imports/{run_id}/quality-report
```

## 11. 外部 Agent 输出规则

外部 Agent 生成导入文件时请遵守：

- 优先使用规范英文字段名，例如 `canonical_name`、`from_entity_name`、`relation_type`，减少字段映射歧义。
- 如果已知 `entity_id`，关系文件优先输出 `from_entity_id` 和 `to_entity_id`；否则输出名称，并同时导出 `entities.csv`。
- `confirmed_relationships.csv` 必须提供 `relation_type`，且每条关系必须能解析到两个不同主体。
- 所有数字字段只输出数字或留空，不要输出 `约3票`、`8 TEU`、`N/A` 这类混合文本。
- `decision_note` 必须写清外部 Agent 的证据来源、人工确认来源或判断规则，不要只写“AI判断”。
- 对未确认、弱证据、冲突证据输出到 `relationship_candidates.csv`，不要输出到 `confirmed_relationships.csv`。
- 对已明确否定的关系，若需要沉淀为最终结论，可在 `confirmed_relationships.csv` 中使用 `relation_type=rejected_relation` 或 `relation_status=rejected`，并在 `decision_note` 写明否定原因。

## 12. 只读复用核心数据表

调用项目只读复用关系时，只需要理解以下表：

| 表 | 用途 |
| --- | --- |
| `entity` | 企业主体主表，核心字段是 `entity_id`、`canonical_name`、`country`、`entity_type`、`status` |
| `entity_alias` | 企业别名表，用于从原始企业名、清洗名、历史名匹配到 `entity_id` |
| `curated_relationship` | 人工确认、已确认文件导入、否定、待验证或人工新增的最终关系表 |
| `relationship_decision` | 人工审核和已确认关系导入记录，可查看谁在何时因为什么原因确认或否定 |
| `relationship_claim` | 系统或外部候选关系，只能作为提示，不应直接当作已确认关系 |

最可信来源是 `curated_relationship`。

## 13. 最小接入清单

给另一个项目或 Agent 接入时，只需要确认：

- 已读取本文档：`D:\Github\trade-entity-graph\docs\local-relationship-reuse-guide.md`。
- 已拿到 SQLite 路径：`D:\Github\trade-entity-graph\data\processed\trade_entity_graph.db`。
- 只读复用时，使用 `mode=ro` 打开数据库。
- 导入写入时，只生成 CSV/Excel 文件，并通过 Streamlit 或 `/imports/run` 交给本项目导入。
- 生成关系文件时，企业名称必须能解析到 `entity_id`；不确定时同时导出 `entities.csv`。
- 只把 `verified` 和 `manual_only` 当作正向确认结论，把 `rejected` 当作反向确认结论。
- `same_entity` 用于主体归并，`same_group` 用于集团识别，不要混用。
