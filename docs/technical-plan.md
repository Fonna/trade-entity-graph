# MVP 技术方案拆解
## 2026-06-08 M11 Technical Update

- Added graph analytics and opportunity discovery on top of existing relationship edge tables.
- `analyze_graph_opportunities()` returns relationship clusters, bridge entities, customer opportunity lists, and high-potential relationship candidates.
- `GET /analytics/opportunities` exposes M11 analysis with `limit`, `min_score`, and `include_rejected`.
- Streamlit adds a `机会发现` tab for M11 summary metrics and opportunity tables.
- Latest verification: `218 passed`, ruff 0 errors.

## 2026-06-03 Technical Update

- Added `relationship_external_evidence` for structured non-order evidence such as public information, sales feedback, business documents, and manual notes.
- `get_relationship_evidence()` returns order-role evidence and supplemental evidence, separated by `evidence_record_type`.
- `POST /relationships/{relationship_id}/external-evidence` appends evidence to a candidate or curated relationship; review/manual-create requests can include `external_evidence`.
- Streamlit separates order evidence and supplemental evidence in relationship details and adds optional evidence inputs on review forms.
- P1 auxiliary order-role edges `shipper_to_notify` / `consignee_to_notify` are implemented. Latest 2026-06-03 verification: `208 passed`, ruff 0 errors.

本文档承接 PRD 与 MVP 研发任务，用于明确第一版工程架构、数据模型、API、页面和开发顺序。

## 1. 架构选择

MVP 采用轻量本地架构：

```text
Excel/CSV 输入
  -> 原始文件归档
  -> Python 导入与清洗
  -> SQLite 核心表
  -> 关系候选聚合服务
  -> NetworkX 局部图查询
  -> FastAPI 接口
  -> Streamlit MVP 页面
  -> CSV/Excel 导出
```

选择理由：

- 当前首要目标是验证业务闭环，而不是大规模图数据库性能；
- SQLite + 边表足以支撑单机 MVP、演示数据和人工审核；
- NetworkX 适合实现一跳、二跳、路径查询和局部图 JSON；
- FastAPI 与 Streamlit 都能复用 Python 数据服务，减少前后端切换成本；
- 表结构保持 PostgreSQL 兼容，后续多人使用时可以迁移。

## 2. 代码模块边界

| 模块 | 路径 | 职责 |
| --- | --- | --- |
| 配置 | `src/trade_entity_graph/config.py` | 读取本地环境、数据库路径、导入归档根目录、规则版本、字段映射版本 |
| 数据库 | `src/trade_entity_graph/db/` | SQLite 连接、schema、迁移脚本和初始化 |
| 导入 | `src/trade_entity_graph/importers/` | Excel/CSV 读取、原始文件归档、字段映射、企业加载、订单证据加载、候选导入、已确认关系导入 |
| 服务 | `src/trade_entity_graph/services/` | 企业搜索、关系聚合、图查询、审核写回、导出 |
| API | `src/trade_entity_graph/api/` | FastAPI app 和 REST routers |
| UI | `src/trade_entity_graph/ui/` | Streamlit MVP 页面 |
| 工具 | `src/trade_entity_graph/utils/` | 名称归一、ID 生成、日志等通用能力 |
| 脚本 | `scripts/` | 本地初始化、导入、启动 API、启动 UI |
| 测试 | `tests/` | 数据库、导入、图查询、审核和导出测试 |

Python 环境约定：

- 使用 `uv sync --extra dev` 创建和同步项目虚拟环境；
- 使用 `.python-version` 将项目 Python 版本固定为 3.12；
- 使用 `uv run python ...` 启动脚本；
- 使用 `uv run pytest` 运行测试；
- 不使用全局 `pip install`、全局 `pytest` 或手工维护的共享虚拟环境。

## 3. 数据模型

### 3.1 导入批次

`import_batch` 保存每次导入的上下文，用 `run_id` 串联订单证据、企业别名、关系候选和已确认关系导入。

关键字段：`run_id`、`source_file`、`source_path`、`imported_by`、`field_mapping_version`、`rule_version`、`success_rows`、`error_rows`、`error_summary`。

`import_source_file` 保存每次导入的逐文件归档记录。导入流程会把源 Excel/CSV 复制到 `data/raw/imports/<run_id>/`，原文件不移动。

关键字段：`source_file_id`、`run_id`、`source_role`、`original_path`、`archived_path`、`file_name`、`file_size_bytes`、`sha256`、`archived_at`。

### 3.2 企业主体与别名

`entity` 是企业关系系统的主节点；`entity_alias` 保存原始订单名、清洗名、简称、历史名和人工新增别名。

关键规则：

- 所有边、候选、最终关系都绑定 `entity_id`；
- 主体合并不物理删除旧主体，后续需要通过状态和审计记录保留历史；
- 企业搜索必须同时查 `canonical_name` 和 `alias_name`。

### 3.3 订单证据与角色边

`order_evidence` 保存订单级证据；`order_role_edge` 保存同一订单中两个企业基于角色形成的证据边。

P0 角色边：

- `customer_to_shipper`
- `customer_to_consignee`
- `customer_to_notify`
- `shipper_to_consignee`

P1 角色边：

- `shipper_to_notify`
- `consignee_to_notify`

订单角色边只表达“共同出现在订单中且角色关系成立”，不能直接当作最终企业关系。

### 3.4 关系候选

`relationship_claim` 保存系统基于订单共现、角色强度、TEU、目的国、产品、名称信号等生成的候选关系。

已有关系候选文件也写入 `relationship_claim`。这类导入只表示“待审核线索”，不能直接进入最终关系。

P0 字段能力：

- 企业对：`from_entity_id`、`to_entity_id`；
- 候选类型：`candidate_relation_type`；
- 状态：`candidate`、`pending_verify` 等；
- 评分：`confidence_level`、`confidence_score`；
- 统计：`order_count`、`total_teu`、角色组合、目的国、产品；
- 解释：`recommendation_reason`。

### 3.5 最终关系与人工决策

`curated_relationship` 保存业务认可的关系结论，`relationship_decision` 保存每次人工审核动作。

已确认关系文件通过独立导入入口写入 `curated_relationship`，不进入 `relationship_claim`。导入时默认 `relation_status=verified`、`source_type=imported_confirmed`、`verified_by=imported_by`，同时写入 `relationship_decision.action_type=import_confirmed` 和 `audit_log.action_type=import_confirmed`。文件必须提供可解析的起点企业、终点企业和 `relation_type`；未知企业、自己连自己、缺少关系类型和非法数值仍进入导入质量闭环。

最终关系状态：`candidate`、`pending_verify`、`verified`、`rejected`、`conflict`、`deprecated`、`manual_only`。

最终关系类型：`same_entity`、`same_group`、`subsidiary`、`factory_node`、`sales_center`、`trading_partner`、`logistics_service`、`co_order_role`、`rejected_relation`、`unknown`。

人工动作必须写入动作类型、修改前后类型、修改前后状态、修改前后置信度、判断理由、操作人和操作时间。

## 4. API 设计

| API | 方法 | 职责 |
| --- | --- | --- |
| `/health` | GET | 返回服务状态 |
| `/entities/search?q=` | GET | 按标准名、别名、原始名搜索企业 |
| `/entities/{entity_id}` | GET | 返回企业详情、别名、标签和统计 |
| `/entities/{entity_id}/neighbors` | GET | 返回中心企业一跳关系 |
| `/entities/{entity_id}/ego-graph` | GET | 返回中心企业图谱 `nodes` / `edges` JSON |
| `/relationships/{relationship_id}` | GET | 返回关系详情 |
| `/relationships/{relationship_id}/evidence` | GET | 返回订单证据和人工记录 |
| `/relationships/{relationship_id}/decision` | POST | 支持确认、否定、修改关系 |
| `/relationships/manual` | POST | 支持人工新增关系 |
| `/reviews/queue` | GET | P1，按状态、批次、关键词和置信等级查看全局待审核候选关系 |
| `/exports/relationships` | POST | 导出关系明细 Excel/CSV |
| `/imports/run` | POST | 触发导入、订单角色边生成、候选聚合和已确认关系直导，返回 `run_id`、统计信息、`curated_relationship_count` 和 `archived_files` |
| `/paths?from_entity_id=&to_entity_id=` | GET | P1，返回两个企业之间的关系路径，支持 `max_depth`、`max_paths` 和 `include_rejected` |
| `/imports` | GET | P1，查看导入批次 |
| `/analytics/opportunities` | GET | P2，返回关系群组、桥接主体、客户机会清单和高潜关系候选，支持 `limit`、`min_score` 和 `include_rejected` |

### Ego Graph 返回结构

```json
{
  "center_entity_id": "ENT_000001",
  "nodes": [
    {
      "id": "ENT_000001",
      "label": "Company A",
      "entity_type": "customer",
      "tags": ["key_customer"],
      "order_count": 12
    }
  ],
  "edges": [
    {
      "id": "REL_000001",
      "source": "ENT_000001",
      "target": "ENT_000002",
      "edge_type": "curated_relationship",
      "relation_type": "trading_partner",
      "status": "verified",
      "order_count": 8,
      "teu": 42
    }
  ]
}
```

### 人工审核写入规则

`POST /relationships/{relationship_id}/decision` 必须满足：

- 不修改原始订单证据；
- 写入或更新 `curated_relationship`；
- 新增 `relationship_decision`；
- 新增 `audit_log`；
- 确认、否定、修改都必须填写理由、操作人和置信度。

## 5. 前端页面设计

MVP 使用 Streamlit 快速实现，后续可迁移 React + AntV G6/Cytoscape.js。

| 页面/模块 | P0 功能 |
| --- | --- |
| 首页/导入页 | 输入本地订单、企业、候选关系和已确认关系文件路径，触发导入，展示成功行数、异常行数、`run_id` 和原始文件归档路径 |
| 企业搜索页 | 输入关键词搜索标准名、原始名、清洗名和别名，点击企业进入详情或图谱 |
| 企业详情页 | 展示主体信息、别名、订单统计、关系统计、最近证据和最近人工决策 |
| 关系图谱页 | 展示中心企业一跳关系，按节点类型、边类型、关系状态编码，默认隐藏 `rejected` |
| 关系详情面板 | 点击边展示关系类型、状态、置信度、订单数、TEU、目的国、产品、证据和历史决策 |
| 全局待审核队列 | 跨企业展示候选、历史匹配、历史冲突和待验证关系，支持按批次、关键词、状态和置信等级筛选；审核成功后自动刷新队列 |
| 人工审核表单 | 确认、否定、修改关系类型、补充证据，提交时强制填写理由和操作人 |
| 人工新增关系表单 | 选择两个企业并新增 `manual_only` 或 `verified` 关系 |
| 机会发现 | 展示 M11 关系群组、桥接主体、客户机会和高潜关系候选 |
| 导出按钮 | 导出当前中心企业关系明细，可选是否包含订单证据和人工决策 |

## 6. 图查询策略

MVP 不加载全图做复杂实时分析，优先局部查询：

1. 根据中心 `entity_id` 从 `order_role_edge` 与 `curated_relationship` 查询相关边；
2. 将查询结果构造成 NetworkX graph；
3. 根据深度、边类型、状态过滤生成子图；
4. 转换为前端 `nodes` / `edges` JSON；
5. 对二跳查询设置最大节点数，超过阈值要求用户增加筛选条件。

## 7. 测试策略

测试优先覆盖闭环风险：

- 数据库初始化：核心表和索引存在；
- 企业导入：样例企业生成主体和别名；
- 原始文件归档：导入时生成 `import_source_file`，归档路径存在，SHA256 长度正确，测试归档根目录隔离在 `tmp_path`；
- 订单证据导入：样例订单写入 `order_evidence`；
- 订单角色边：客户 -> 通知人等核心边正确生成；
- 候选聚合：多条订单边聚合为一条候选；
- 图查询：中心企业一跳图返回正确节点和边；
- 审核写回：确认和否定都写入最终关系与决策记录；
- 导出：中心企业关系明细可生成 CSV/Excel。
- 导入质量：真实数据试运行保留有效行，字段缺失、非法数值和未知企业等异常可查询、可导出；
- 路径查询：二跳展开和两企业路径查询支持深度、路径数、节点上限和 `include_rejected` 控制；
- 机会发现：M11 分析返回关系群组、桥接主体、客户机会和高潜关系候选，并验证 `limit`、`min_score` 和空图谱场景。

## 8. 开发顺序

1. 完成 M0 脚手架、README、任务清单和技术方案；
2. 完成 M1 schema 测试和数据库初始化；
3. 完成 M2 导入前预检查、字段映射、主体和订单证据加载；
4. 完成 M3 订单角色边生成；
5. 完成 M4 候选关系聚合与评分；
6. 完成 M5 图查询服务；
7. 完成 M6 API；
8. 完成 M7 Streamlit 页面；
9. 完成 M8 演示数据、导出和验收；
10. 完成 M9 真实数据试运行、导入质量报告和异常闭环；
11. 完成 M10 二跳图谱、两企业路径查询和 Streamlit 路径查询；
12. 完成 M11 图谱分析、机会发现 API 和 Streamlit 机会发现页。

## 9. 当前开发记录

截至 2026-06-08，当前分支已完成 M2-M11 P0/P1/P2 闭环、导入源文件归档、历史关系复用、中文工作台收口、真实数据导入质量闭环、二跳图谱/路径查询和机会发现：

- M2：导入企业、订单、已有关系候选和已确认关系，记录 `import_batch` 和 `import_source_file`。
- M3/M4：生成 P0 订单角色边并聚合关系候选。
- M5：提供实体、关系、图谱、审核和导出服务。
- M6：提供 FastAPI P0 endpoint，`/imports/run` 返回 `archived_files`，并提供 `/reviews/queue` 全局待审核队列。
- M7：提供中文 Streamlit 工作台，并在顶部展示基础逻辑与使用方法；表格字段和常见后端错误已面向业务用户中文化；新增待审核队列 tab 支持跨企业集中审核，审核成功后自动刷新队列。
- M8：提供可重复生成的演示数据包、预置审核脚本和历史人工判断复用能力。
- M9：提供字段映射、导入异常、批次查询、质量报告和异常 CSV 导出。
- M10：提供受控二跳展开、两企业路径查询和 Streamlit 路径步骤表。
- M11：在现有边表上提供图谱分析/机会发现，识别关系群组、桥接主体、客户机会清单和高潜关系候选，并接入 FastAPI 与 Streamlit。

最近一次验证：

```powershell
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff check .
```

结果：全量测试 218 passed，ruff 0 errors。

## 10. 后续演进

- SQLite -> PostgreSQL：多人协作、权限和并发写入增强；
- Streamlit -> React：稳定需求后产品化页面；
- NetworkX 局部图 -> 轻量图数据库或 Neo4j：当路径查询、聚类、全图分析变成核心需求；
- 人工公网验证结果结构化写回；
- BI、CRM 或飞书多维表集成；
- 关系变更提醒和客户机会监控。
