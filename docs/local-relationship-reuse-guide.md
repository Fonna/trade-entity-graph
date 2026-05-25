# 本机企业主体关系复用使用文档

本文档面向同一台电脑上的其他项目，用于只读复用 `trade-entity-graph` 已沉淀的企业主体、别名和人工确认关系，辅助判断两个企业是否为同主体、同集团或其他已确认关系。

## 1. 使用边界

当前推荐方式是：其他项目只读访问本项目 SQLite 数据库，不直接修改关系数据。

适合场景：

- 另一个本机 Python 项目需要判断两个企业是否已确认同主体或同集团。
- 批量处理订单、客户、收发货人、通知人时，需要复用历史人工确认结论。
- 调用项目只需要关系判断结果，不参与关系审核、证据维护或主体合并。

不建议调用项目做的事情：

- 不要直接写入 `curated_relationship`、`relationship_decision`、`entity`、`entity_alias`。
- 不要把订单共现关系直接当作最终企业关系。
- 不要默认把 `A-B same_group`、`B-C same_group` 推导成 `A-C same_group`，除非业务明确允许集团连通推断。

## 2. 数据库位置

默认数据库路径：

```text
D:\Github\trade-entity-graph\data\processed\trade_entity_graph.db
```

如果本项目运行时配置过 `TEG_DATABASE_PATH`，应以该环境变量指向的数据库为准。

建议调用项目通过配置文件或环境变量保存数据库路径，例如：

```powershell
$env:TEG_RELATIONSHIP_DB="D:\Github\trade-entity-graph\data\processed\trade_entity_graph.db"
```

## 3. 核心数据表

调用项目只需要理解以下表：

| 表 | 用途 |
| --- | --- |
| `entity` | 企业主体主表，核心字段是 `entity_id`、`canonical_name`、`country`、`entity_type`、`status` |
| `entity_alias` | 企业别名表，用于从原始企业名、清洗名、历史名匹配到 `entity_id` |
| `curated_relationship` | 人工确认、否定、待验证或人工新增的最终关系表 |
| `relationship_decision` | 人工审核记录，可用于查看谁在何时因为什么原因确认或否定 |
| `relationship_claim` | 系统候选关系，只能作为提示，不应直接当作已确认关系 |

最重要的可信来源是 `curated_relationship`。

## 4. 关系类型解释

调用项目判断时重点关注以下 `relation_type`：

| relation_type | 含义 | 调用项目建议动作 |
| --- | --- | --- |
| `same_entity` | 同一企业主体 | 可用于客户去重、订单归并、企业名归一 |
| `same_group` | 同集团 | 可用于集团客户识别、关系网络、销售机会分析；不要合并成同一主体 |
| `subsidiary` | 子公司或海外公司 | 可作为强组织关系使用，注意方向 |
| `factory_node` | 海外工厂或生产节点 | 可用于海外节点识别和机会分析 |
| `sales_center` | 销售中心 | 可用于销售网络识别 |
| `trading_partner` | 普通贸易伙伴 | 只表示业务往来关系 |
| `logistics_service` | 物流、货代、仓储、清关等服务关系 | 一般不作为集团或主体关系 |
| `rejected_relation` | 已否定关系 | 表示历史审核明确否定，不要自动推断成正向关系 |

## 5. 关系状态解释

调用项目应优先信任以下状态：

| relation_status | 含义 | 是否可作为确认结论 |
| --- | --- | --- |
| `verified` | 已确认关系 | 是 |
| `manual_only` | 人工新增关系，可能暂无订单证据 | 是 |
| `rejected` | 已否定关系 | 是，但表示反向结论 |
| `pending_verify` | 待进一步验证 | 否，只能提示 |
| `conflict` | 证据冲突 | 否，需要人工处理 |
| `deprecated` | 历史关系，已被替代 | 否 |
| `candidate` | 系统候选 | 否 |

建议判断优先级：

```text
1. 命中 rejected：返回 rejected，表示已明确否定。
2. 命中 same_entity + verified/manual_only：返回 same_entity。
3. 命中 same_group + verified/manual_only：返回 same_group。
4. 命中其他 verified/manual_only 关系：返回对应关系类型。
5. 只命中 candidate/pending_verify/conflict：返回 uncertain。
6. 完全未命中：返回 unknown。
```

## 6. 推荐返回结构

调用项目内部可以统一返回以下结构，便于后续扩展：

```json
{
  "matched": true,
  "result": "same_group",
  "from_entity_id": "ENT_xxx",
  "from_name": "COMPANY A",
  "to_entity_id": "ENT_yyy",
  "to_name": "COMPANY B",
  "relationship_id": "REL_xxx",
  "relation_type": "same_group",
  "relation_status": "verified",
  "confidence_level": "high",
  "confidence_score": 0.91,
  "decision_note": "人工确认两家公司属于同一集团",
  "verified_by": "local_user",
  "verified_at": "2026-05-25 10:30:00"
}
```

未命中时建议返回：

```json
{
  "matched": false,
  "result": "unknown",
  "reason": "No confirmed relationship found"
}
```

## 7. Python 只读调用示例

下面代码可直接复制到另一个 Python 项目中作为最小只读判断工具。

```python
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = r"D:\Github\trade-entity-graph\data\processed\trade_entity_graph.db"
CONFIRMED_STATUSES = {"verified", "manual_only"}
NEGATIVE_STATUSES = {"rejected"}
SPACES = re.compile(r"\s+")


def normalize_company_name(value: str | None) -> str:
    if not value:
        return ""
    return SPACES.sub(" ", value.strip()).upper()


def connect_readonly(db_path: str | Path | None = None) -> sqlite3.Connection:
    target = Path(db_path or os.getenv("TEG_RELATIONSHIP_DB") or DEFAULT_DB_PATH).resolve()
    uri = f"file:{target.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def resolve_entity(connection: sqlite3.Connection, company_name: str) -> dict[str, Any] | None:
    normalized = normalize_company_name(company_name)
    if not normalized:
        return None

    row = connection.execute(
        """
        SELECT entity_id, canonical_name, country, entity_type, status, 0 AS match_rank
        FROM entity
        WHERE UPPER(canonical_name) = ?
        UNION ALL
        SELECT e.entity_id, e.canonical_name, e.country, e.entity_type, e.status, 1 AS match_rank
        FROM entity_alias a
        JOIN entity e ON e.entity_id = a.entity_id
        WHERE UPPER(a.alias_name) = ?
        ORDER BY match_rank, canonical_name
        LIMIT 1
        """,
        (normalized, normalized),
    ).fetchone()
    return dict(row) if row else None


def get_curated_relationship(
    connection: sqlite3.Connection,
    from_entity_id: str,
    to_entity_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT cr.relationship_id,
               cr.from_entity_id,
               e1.canonical_name AS from_name,
               cr.to_entity_id,
               e2.canonical_name AS to_name,
               cr.relation_type,
               cr.relation_status,
               cr.confidence_level,
               cr.confidence_score,
               cr.source_type,
               cr.decision_source,
               cr.decision_note,
               cr.verified_by,
               cr.verified_at,
               cr.updated_at
        FROM curated_relationship cr
        JOIN entity e1 ON e1.entity_id = cr.from_entity_id
        JOIN entity e2 ON e2.entity_id = cr.to_entity_id
        WHERE (
            cr.from_entity_id = ? AND cr.to_entity_id = ?
        ) OR (
            cr.from_entity_id = ? AND cr.to_entity_id = ?
        )
        ORDER BY
            CASE cr.relation_status
                WHEN 'rejected' THEN 0
                WHEN 'verified' THEN 1
                WHEN 'manual_only' THEN 2
                ELSE 9
            END,
            cr.updated_at DESC
        LIMIT 1
        """,
        (from_entity_id, to_entity_id, to_entity_id, from_entity_id),
    ).fetchone()
    return dict(row) if row else None


def judge_entity_relationship(
    company_a: str,
    company_b: str,
    *,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    with connect_readonly(db_path) as connection:
        entity_a = resolve_entity(connection, company_a)
        entity_b = resolve_entity(connection, company_b)

        if not entity_a or not entity_b:
            return {
                "matched": False,
                "result": "unknown_entity",
                "entity_a": entity_a,
                "entity_b": entity_b,
                "reason": "At least one company name did not resolve to an entity",
            }

        if entity_a["entity_id"] == entity_b["entity_id"]:
            return {
                "matched": True,
                "result": "same_entity",
                "from_entity_id": entity_a["entity_id"],
                "from_name": entity_a["canonical_name"],
                "to_entity_id": entity_b["entity_id"],
                "to_name": entity_b["canonical_name"],
                "reason": "Both names resolved to the same entity_id",
            }

        relationship = get_curated_relationship(
            connection,
            entity_a["entity_id"],
            entity_b["entity_id"],
        )
        if not relationship:
            return {
                "matched": False,
                "result": "unknown",
                "from_entity_id": entity_a["entity_id"],
                "from_name": entity_a["canonical_name"],
                "to_entity_id": entity_b["entity_id"],
                "to_name": entity_b["canonical_name"],
                "reason": "No curated relationship found",
            }

        status = relationship["relation_status"]
        relation_type = relationship["relation_type"]

        if status in NEGATIVE_STATUSES:
            result = "rejected"
        elif status in CONFIRMED_STATUSES:
            result = relation_type
        else:
            result = "uncertain"

        return {
            "matched": result not in {"unknown", "uncertain"},
            "result": result,
            **relationship,
        }


if __name__ == "__main__":
    result = judge_entity_relationship("Company A", "Company B")
    print(result)
```

## 8. 常用 SQL

### 8.1 按企业名解析主体

```sql
SELECT DISTINCT e.entity_id, e.canonical_name, e.country, e.entity_type, e.status
FROM entity e
LEFT JOIN entity_alias a ON a.entity_id = e.entity_id
WHERE UPPER(e.canonical_name) LIKE UPPER('%APEX%')
   OR UPPER(a.alias_name) LIKE UPPER('%APEX%')
ORDER BY e.canonical_name
LIMIT 20;
```

### 8.2 查询两个主体之间的最终关系

```sql
SELECT cr.relationship_id,
       cr.from_entity_id,
       e1.canonical_name AS from_name,
       cr.to_entity_id,
       e2.canonical_name AS to_name,
       cr.relation_type,
       cr.relation_status,
       cr.confidence_level,
       cr.confidence_score,
       cr.decision_note,
       cr.verified_by,
       cr.verified_at
FROM curated_relationship cr
JOIN entity e1 ON e1.entity_id = cr.from_entity_id
JOIN entity e2 ON e2.entity_id = cr.to_entity_id
WHERE (cr.from_entity_id = 'ENT_A' AND cr.to_entity_id = 'ENT_B')
   OR (cr.from_entity_id = 'ENT_B' AND cr.to_entity_id = 'ENT_A')
ORDER BY cr.updated_at DESC;
```

### 8.3 导出所有已确认同主体关系

```sql
SELECT cr.relationship_id,
       cr.from_entity_id,
       e1.canonical_name AS from_name,
       cr.to_entity_id,
       e2.canonical_name AS to_name,
       cr.relation_type,
       cr.relation_status,
       cr.verified_by,
       cr.verified_at,
       cr.decision_note
FROM curated_relationship cr
JOIN entity e1 ON e1.entity_id = cr.from_entity_id
JOIN entity e2 ON e2.entity_id = cr.to_entity_id
WHERE cr.relation_type = 'same_entity'
  AND cr.relation_status IN ('verified', 'manual_only');
```

### 8.4 导出所有已确认同集团关系

```sql
SELECT cr.relationship_id,
       cr.from_entity_id,
       e1.canonical_name AS from_name,
       cr.to_entity_id,
       e2.canonical_name AS to_name,
       cr.relation_type,
       cr.relation_status,
       cr.verified_by,
       cr.verified_at,
       cr.decision_note
FROM curated_relationship cr
JOIN entity e1 ON e1.entity_id = cr.from_entity_id
JOIN entity e2 ON e2.entity_id = cr.to_entity_id
WHERE cr.relation_type = 'same_group'
  AND cr.relation_status IN ('verified', 'manual_only');
```

### 8.5 查询已否定关系

```sql
SELECT cr.relationship_id,
       cr.from_entity_id,
       e1.canonical_name AS from_name,
       cr.to_entity_id,
       e2.canonical_name AS to_name,
       cr.relation_type,
       cr.relation_status,
       cr.decision_note,
       cr.verified_by,
       cr.verified_at
FROM curated_relationship cr
JOIN entity e1 ON e1.entity_id = cr.from_entity_id
JOIN entity e2 ON e2.entity_id = cr.to_entity_id
WHERE cr.relation_status = 'rejected'
   OR cr.relation_type = 'rejected_relation';
```

## 9. 通过本项目服务复用

如果调用项目不想直接连接 SQLite，也可以在本机启动本项目 FastAPI 服务，然后通过 HTTP 调用。

启动方式：

```powershell
cd D:\Github\trade-entity-graph
uv --cache-dir .uv-cache run python scripts\run_api.py
```

当前可用接口示例：

```text
GET  http://127.0.0.1:8000/entities/search?q=APEX
GET  http://127.0.0.1:8000/entities/{entity_id}
GET  http://127.0.0.1:8000/entities/{entity_id}/ego-graph
GET  http://127.0.0.1:8000/relationships/{relationship_id}
GET  http://127.0.0.1:8000/relationships/{relationship_id}/evidence
POST http://127.0.0.1:8000/exports/relationships
```

导出某个中心企业的关系：

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://127.0.0.1:8000/exports/relationships" `
  -ContentType "application/json" `
  -Body '{"center_entity_id":"ENT_xxx","include_rejected":false}'
```

HTTP 方式适合非 Python 项目或后续需要统一服务化；本机 Python 项目短期建议优先使用只读 SQLite。

## 10. 调用方判断建议

调用项目可按以下业务含义使用结果：

```text
same_entity:
  可视为同一主体，用于企业去重、客户归并、订单归并。

same_group:
  可视为同一集团或强组织关联，用于集团客户识别和机会分析。
  不应直接合并企业主体。

subsidiary / factory_node / sales_center:
  可视为组织网络关系，适合关系图谱、机会分析、海外节点判断。

trading_partner:
  只表示业务伙伴或贸易往来，不代表同集团。

logistics_service:
  通常应作为物流服务节点处理，不代表客户集团关系。

rejected:
  表示历史审核明确否定，应阻止自动推断成同主体或同集团。

unknown / uncertain:
  调用项目可以继续走自己的规则，也可以进入待验证队列。
```

## 11. 数据更新约定

其他项目读取的是当前 SQLite 中的最新审核结果。

建议约定：

- 本项目完成新一批导入和人工审核后，其他项目再运行批量判断。
- 调用项目只读打开数据库，避免误写。
- 如果判断结果影响正式业务动作，应记录返回的 `relationship_id`、`relation_type`、`relation_status`、`verified_at`，方便后续追溯。
- 如果调用项目发现关系缺失或疑似错误，不要直接修改数据库，应回到本项目走关系审核或人工新增流程。

## 12. 最小接入清单

给另一个项目接入时，只需要确认：

- 已拿到 SQLite 路径：`D:\Github\trade-entity-graph\data\processed\trade_entity_graph.db`
- 只读连接数据库。
- 企业名先解析到 `entity_id`，再判断关系。
- 只把 `verified` 和 `manual_only` 当作正向确认结论。
- 把 `rejected` 当作反向确认结论。
- `same_entity` 用于主体归并，`same_group` 用于集团识别，不能混用。
