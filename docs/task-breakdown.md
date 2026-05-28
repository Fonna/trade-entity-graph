# MVP 研发任务清单

本文档基于 `企业关系图谱系统_PRD.md` 与 `MVP研发任务拆解.md` 整理，用于后续开发排期、Issue 拆分和验收跟踪。

## 1. 目标闭环

MVP 第一版只承诺 P0 闭环：

1. 导入当前项目订单分析 Excel 与企业清洗结果；
2. 生成企业主体、别名、订单证据和订单角色边；
3. 聚合企业对，生成可解释的关系候选；
4. 支持人工确认、否定、修改、补充证据和人工新增关系；
5. 将人工结果写入最终关系与决策记录；
6. 支持企业搜索、中心企业一跳图谱、关系详情和导出。

## 2. 里程碑

| 里程碑 | 名称 | 目标 | 优先级 | 验收口径 |
| --- | --- | --- | --- | --- |
| M0 | 项目脚手架与基础规范 | 建立 Python 项目、目录结构、README、配置、基础 schema 和 smoke test | P0 | 通过 `uv sync --extra dev` 安装依赖，`uv run pytest` 可跑基础测试，`uv run python scripts/init_db.py` 可初始化数据库 |
| M1 | 数据库 schema 与初始化 | 建立核心表、索引和初始化脚本 | P0 | SQLite 中存在核心表，表结构覆盖 PRD 关键字段 |
| M2 | 数据导入与字段映射 | 读取订单分析 Excel/CSV、企业清洗结果和关系候选结果 | P0 | 能生成 `import_batch`、`entity`、`entity_alias`、`order_evidence` |
| M3 | 订单角色边生成 | 生成客户/发货人/收货人/通知人的核心角色边 | P0 | 至少支持 4 类核心边，且每条边可追溯订单证据 |
| M4 | 关系候选聚合 | 基于边表聚合企业对、计算基础评分和推荐理由 | P0 | 相同企业对可聚合成候选，展示订单数、TEU、目的国、产品信号 |
| M5 | 图查询服务 | 使用 NetworkX/边表查询中心企业一跳关系 | P0 | API 可返回 `nodes` / `edges` JSON，默认隐藏 `rejected` |
| M6 | FastAPI 接口 | 提供搜索、详情、图谱、审核写入、全局待审核队列、导出接口 | P0 | P0 API 可通过最小样例验证 |
| M7 | Streamlit MVP 页面 | 提供导入、搜索、图谱、详情、待审核队列、审核、导出原型页面 | P0 | 用户可完成演示脚本中的核心路径 |
| M8 | 验收与演示数据 | 准备样例数据、导出结果、测试清单和演示流程 | P0 | PRD 功能验收与业务验收 P0 项通过 |
| M9 | 真实数据试运行与导入质量闭环 | 支持真实文件字段映射、行级异常沉淀、批次查询、质量报告和异常导出 | P1 | 真实脏数据可部分导入，异常可追溯、可查询、可导出 |

## 3. 数据库任务

| ID | 任务 | 优先级 | 产出 | 验收标准 |
| --- | --- | --- | --- | --- |
| DB-01 | 创建 `entity` 表 | P0 | `src/trade_entity_graph/db/schema.sql` | 保存企业主体、国家、类型、标签、状态 |
| DB-02 | 创建 `entity_alias` 表 | P0 | `schema.sql` | 标准名、原始名、清洗名和别名可关联 `entity_id` |
| DB-03 | 创建 `order_evidence` 表 | P0 | `schema.sql` | 可追溯订单号、源文件、sheet、行号、TEU、目的地、产品 |
| DB-04 | 创建 `order_role_edge` 表 | P0 | `schema.sql` | 可保存下单客户到通知人等订单角色关系 |
| DB-05 | 创建 `relationship_claim` 表 | P0 | `schema.sql` | 可保存系统生成的关系候选、评分和推荐理由 |
| DB-06 | 创建 `curated_relationship` 表 | P0 | `schema.sql` | 可保存人工确认、否定、待验证、人工新增关系 |
| DB-07 | 创建 `relationship_decision` 表 | P0 | `schema.sql` | 记录每次人工操作的前后状态和理由 |
| DB-08 | 创建 `import_batch` 表 | P0 | `schema.sql` | 每次导入有唯一 `run_id` 并记录源文件和规则版本 |
| DB-09 | 创建 `audit_log` 表 | P0 | `schema.sql` | 关键人工操作可追溯 |
| DB-10 | 添加常用索引 | P0 | `schema.sql` | 支持企业搜索、边查询、关系详情查询 |
| DB-11 | 创建 `import_source_file` 表 | P0 | `schema.sql` | 每个导入源文件可记录角色、原始路径、归档路径、文件大小和 SHA256 |

## 4. 数据导入任务

| ID | 任务 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| IMP-01 | 支持读取订单标准化明细 Excel | P0 | 能识别 workbook/sheet 并读取行数 |
| IMP-02 | 支持读取企业清洗结果 | P0 | 原始名、清洗名、标准名可映射到 `entity_id` |
| IMP-03 | 支持读取已有关系候选结果 | P0 | 可生成 `relationship_claim` |
| IMP-04 | 生成导入批次 `run_id` | P0 | 可按 `run_id` 查询导入结果 |
| IMP-05 | 字段映射配置 | P1 | 字段名变化时不改代码即可适配 |
| IMP-06 | 异常行记录 | P1 | 字段缺失、企业无法匹配、TEU 异常可导出复核 |
| IMP-07 | 原始文件归档 | P0 | 导入时复制源文件到 `data/raw/imports/<run_id>/`，原文件不移动，并写入 `import_source_file` |

## 5. 订单角色边任务

| ID | 任务 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| EDGE-01 | 生成下单客户 -> 发货人边 | P0 | 边表存在 `customer_to_shipper` 记录和订单证据 |
| EDGE-02 | 生成下单客户 -> 收货人边 | P0 | 边表存在 `customer_to_consignee` 记录和订单证据 |
| EDGE-03 | 生成下单客户 -> 通知人边 | P0 | 边表存在 `customer_to_notify` 记录和订单证据 |
| EDGE-04 | 生成发货人 -> 收货人边 | P0 | 边表存在 `shipper_to_consignee` 记录和订单证据 |
| EDGE-05 | 排除无效主体和占位符 | P0 | `SAME AS`、`TO ORDER`、YQN 自身等不生成无意义边 |
| EDGE-06 | 聚合企业对统计 | P0 | 可统计订单数、TEU、目的国、产品和角色组合 |
| EDGE-07 | 生成发货人 -> 通知人边 | P1 | 可作为辅助证据展示 |
| EDGE-08 | 生成收货人 -> 通知人边 | P1 | 可作为辅助证据展示 |

## 6. 关系候选与最终关系任务

| ID | 任务 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| REL-01 | 基于订单角色边生成关系候选 | P0 | 相同企业对可聚合为一条候选 |
| REL-02 | 支持候选关系类型枚举 | P0 | 类型受控，如 `trading_partner_candidate`、`factory_candidate` |
| REL-03 | 计算基础置信度 | P0 | 每条候选有分数或高/中/低等级 |
| REL-04 | 生成推荐理由 | P0 | 前端可解释订单数、TEU、目的国、产品等信号 |
| CUR-01 | 确认候选关系 | P0 | 生成 `curated_relationship`，状态为 `verified` |
| CUR-02 | 否定候选关系 | P0 | 生成或更新最终关系为 `rejected`，不物理删除 |
| CUR-03 | 修改关系类型 | P0 | 决策记录保存前后类型 |
| CUR-04 | 人工新增关系 | P0 | 无候选时可新增 `manual_only` 或 `verified` 关系 |
| CUR-05 | 补充人工备注和证据 | P1 | 关系详情可查看备注、来源和链接 |
| CUR-06 | 写入审计日志 | P0 | 确认、否定、修改、新增均记录操作人和时间 |

## 7. 图查询任务

| ID | 任务 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| GRAPH-01 | 从边表构建局部图 | P0 | 可读取 `order_role_edge` 和 `curated_relationship` |
| GRAPH-02 | 获取中心企业一跳关系 | P0 | 返回中心企业直接相连节点和边 |
| GRAPH-03 | 支持边类型过滤 | P0 | 可切换订单证据边、候选关系、最终关系 |
| GRAPH-04 | 支持状态过滤 | P0 | 默认隐藏 `rejected`，可查看历史否定关系 |
| GRAPH-05 | 返回图谱摘要 | P1 | 返回节点数、边数、订单数和 TEU |
| GRAPH-06 | 获取中心企业二跳关系 | P1 | 按需展开并限制节点数 |
| GRAPH-07 | 查询 A 到 C 路径 | P1 | 限制深度后返回路径节点和边 |

## 8. API 任务

| ID | API | 方法 | 优先级 | 验收标准 |
| --- | --- | --- | --- | --- |
| API-01 | `/health` | GET | P0 | 返回服务状态 |
| API-02 | `/entities/search?q=` | GET | P0 | 按标准名、别名、原始名搜索企业 |
| API-03 | `/entities/{entity_id}` | GET | P0 | 返回企业详情、别名、标签和统计 |
| API-04 | `/entities/{entity_id}/neighbors` | GET | P0 | 返回一跳关系 |
| API-05 | `/entities/{entity_id}/ego-graph` | GET | P0 | 返回中心企业图谱 JSON |
| API-06 | `/relationships/{relationship_id}` | GET | P0 | 返回关系详情 |
| API-07 | `/relationships/{relationship_id}/evidence` | GET | P0 | 返回订单证据和人工记录 |
| API-08 | `/relationships/{relationship_id}/decision` | POST | P0 | 支持确认、否定、修改关系 |
| API-09 | `/relationships/manual` | POST | P0 | 支持人工新增关系 |
| API-10 | `/exports/relationships` | POST | P0 | 导出关系明细 Excel/CSV |
| API-11 | `/imports/run` | POST | P0 | 触发导入、边生成和候选聚合，并返回 `archived_files` |
| API-12 | `/paths?from=&to=` | GET | P1 | 返回 A 到 C 的关系路径 |
| API-13 | `/imports` | GET | P1 | 查看导入批次 |
| API-14 | `/reviews/queue` | GET | P1 | 按状态、批次、关键词和置信等级查看全局待审核候选关系 |

## 9. 前端页面任务

| ID | 页面/模块 | 优先级 | 验收标准 |
| --- | --- | --- | --- |
| UI-01 | 首页/导入页 | P0 | 可输入本地文件路径、触发导入、查看成功/异常数量、批次号和原始文件归档路径 |
| UI-02 | 企业搜索页 | P0 | 输入企业名后展示匹配主体 |
| UI-03 | 企业详情页 | P0 | 展示主体信息、别名、订单统计和关系统计 |
| UI-04 | 关系图谱页 | P0 | 展示中心企业一跳图谱 |
| UI-05 | 图谱筛选器 | P0 | 按关系类型、状态、边类型过滤 |
| UI-06 | 关系详情面板 | P0 | 点击边展示关系详情和证据摘要 |
| UI-07 | 订单证据表 | P0 | 可追溯订单号、源文件和源行号 |
| UI-08 | 人工审核表单 | P0 | 可确认、否定、修改关系类型并填写备注 |
| UI-09 | 人工新增关系表单 | P0 | 可选择两个企业并新增关系 |
| UI-10 | 导出按钮 | P0 | 可导出当前中心企业关系明细 |
| UI-11 | 二跳展开 | P1 | 节点过多时提示收窄条件 |
| UI-12 | 路径查询 | P1 | 可返回两个企业之间的连接路径 |
| UI-13 | 全局待审核队列 | P1 | 可跨企业查看、筛选并带入人工审核候选关系；审核成功后自动刷新队列 |

## 10. 第一版验收清单

- [x] 能导入至少一份当前项目订单分析 Excel；
- [x] 能导入企业清洗结果并生成企业主体和别名；
- [x] 能生成客户->发货人、客户->收货人、客户->通知人、发货人->收货人四类核心订单角色边；
- [x] 每条订单角色边可追溯到订单、源文件、sheet 和行号；
- [x] 能生成关系候选并聚合订单数、TEU、目的国和产品信号；
- [x] 用户可以搜索企业主体、查看详情和中心企业一跳图谱；
- [x] 用户可以点击关系查看订单证据；
- [x] 用户可以确认、否定、修改和人工新增关系；
- [x] 人工结果写入最终关系、决策记录和审计日志；
- [x] 已否定关系不会被物理删除或被系统自动覆盖；
- [x] 用户可以导出中心企业关系明细。

## 11. 当前实现状态

截至 2026-05-28，仓库已完成 M2-M9 P0/P1 的服务层优先实现、历史关系复用、演示验收数据包和真实数据试运行导入质量闭环：

- M2：支持 Excel/CSV 导入，生成 `import_batch`、`import_source_file`、`entity`、`entity_alias`、`order_evidence`，并可导入已有 `relationship_claim`；导入时会复制原始文件到 `data/raw/imports/<run_id>/`。
- M3：支持生成 `customer_to_shipper`、`customer_to_consignee`、`customer_to_notify`、`shipper_to_consignee` 四类 P0 订单角色边。
- M4：支持从订单角色边聚合候选关系，生成订单数、TEU、角色组合、目的国、产品摘要、置信度和推荐理由。
- M5：支持实体搜索、实体详情、一跳图谱、关系详情、关系证据、审核写回和导出服务。
- M6：支持 P0 FastAPI endpoint，包括导入、搜索、详情、图谱、关系详情、审核、全局待审核队列和导出；`/imports/run` 返回本次导入的 `archived_files`。
- M7：支持中文 Streamlit MVP 工作台 tabs：数据导入、企业搜索、关系图谱、关系详情、待审核队列、人工审核、导出；顶部包含基础逻辑与使用方法说明；表格字段和常见后端错误已面向业务用户中文化；审核成功后会刷新页面以更新待审核队列。
- M8：新增可重复生成的演示数据包和预置审核脚本；演示数据约 50 个主体、80+ 条订单，保留待审核候选关系，并覆盖主要最终关系类型；支持历史人工判断复用、沿用历史、替代历史和标记待验证。
- M9：支持默认字段映射配置、导入行级异常记录、导入批次查询、质量报告和异常 CSV 导出，真实数据试运行时可保留有效行并沉淀坏行原因。

验证命令：

```powershell
uv --cache-dir .uv-cache run pytest
uv --cache-dir .uv-cache run ruff check .
```

当前通过标准：全量测试 164 passed，ruff 0 errors。
