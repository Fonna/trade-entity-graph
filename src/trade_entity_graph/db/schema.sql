-- MVP bootstrap schema for trade-entity-graph.
-- Order evidence is kept separate from curated business relationships.

CREATE TABLE IF NOT EXISTS import_batch (
    run_id TEXT PRIMARY KEY,
    source_file TEXT NOT NULL,
    source_path TEXT,
    imported_by TEXT,
    imported_at TEXT DEFAULT CURRENT_TIMESTAMP,
    field_mapping_version TEXT,
    rule_version TEXT,
    success_rows INTEGER DEFAULT 0,
    error_rows INTEGER DEFAULT 0,
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS entity (
    entity_id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    country TEXT,
    entity_type TEXT,
    tags TEXT,
    status TEXT DEFAULT 'active',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS entity_alias (
    alias_id TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    alias_name TEXT NOT NULL,
    alias_type TEXT NOT NULL,
    source TEXT,
    run_id TEXT REFERENCES import_batch(run_id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_evidence (
    evidence_id TEXT PRIMARY KEY,
    order_id TEXT,
    teu REAL,
    product_name TEXT,
    function_category TEXT,
    destination_country TEXT,
    destination_port TEXT,
    order_date TEXT,
    source_file TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    run_id TEXT REFERENCES import_batch(run_id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_role_edge (
    edge_id TEXT PRIMARY KEY,
    evidence_id TEXT REFERENCES order_evidence(evidence_id),
    order_id TEXT,
    from_entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    from_role TEXT NOT NULL,
    to_entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    to_role TEXT NOT NULL,
    role_pair_type TEXT NOT NULL,
    teu REAL,
    product_name TEXT,
    function_category TEXT,
    destination_country TEXT,
    destination_port TEXT,
    order_date TEXT,
    source_file TEXT,
    source_sheet TEXT,
    source_row INTEGER,
    run_id TEXT REFERENCES import_batch(run_id),
    is_effective_role INTEGER DEFAULT 1,
    evidence_weight REAL DEFAULT 1.0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS relationship_claim (
    claim_id TEXT PRIMARY KEY,
    from_entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    to_entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    candidate_relation_type TEXT NOT NULL,
    direction TEXT DEFAULT 'directed',
    relation_status TEXT DEFAULT 'candidate',
    confidence_level TEXT,
    confidence_score REAL,
    order_count INTEGER DEFAULT 0,
    total_teu REAL DEFAULT 0,
    role_pair_summary TEXT,
    destination_summary TEXT,
    product_summary TEXT,
    recommendation_reason TEXT,
    run_id TEXT REFERENCES import_batch(run_id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS curated_relationship (
    relationship_id TEXT PRIMARY KEY,
    from_entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    to_entity_id TEXT NOT NULL REFERENCES entity(entity_id),
    relation_type TEXT NOT NULL,
    relation_status TEXT NOT NULL,
    confidence_level TEXT,
    confidence_score REAL,
    source_type TEXT,
    decision_source TEXT,
    decision_note TEXT,
    verified_by TEXT,
    verified_at TEXT,
    valid_from TEXT,
    valid_to TEXT,
    supersedes_relationship_id TEXT REFERENCES curated_relationship(relationship_id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS relationship_decision (
    decision_id TEXT PRIMARY KEY,
    relationship_id TEXT REFERENCES curated_relationship(relationship_id),
    claim_id TEXT REFERENCES relationship_claim(claim_id),
    action_type TEXT NOT NULL,
    before_relation_type TEXT,
    after_relation_type TEXT,
    before_status TEXT,
    after_status TEXT,
    before_confidence TEXT,
    after_confidence TEXT,
    reason TEXT NOT NULL,
    evidence_summary TEXT,
    operator TEXT NOT NULL,
    operated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS audit_log (
    audit_id TEXT PRIMARY KEY,
    object_type TEXT NOT NULL,
    object_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    before_value TEXT,
    after_value TEXT,
    operator TEXT NOT NULL,
    operated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_entity_canonical_name ON entity(canonical_name);
CREATE INDEX IF NOT EXISTS idx_entity_alias_name ON entity_alias(alias_name);
CREATE INDEX IF NOT EXISTS idx_order_role_edge_from ON order_role_edge(from_entity_id);
CREATE INDEX IF NOT EXISTS idx_order_role_edge_to ON order_role_edge(to_entity_id);
CREATE INDEX IF NOT EXISTS idx_order_role_edge_role_pair ON order_role_edge(role_pair_type);
CREATE INDEX IF NOT EXISTS idx_relationship_claim_pair ON relationship_claim(from_entity_id, to_entity_id);
CREATE INDEX IF NOT EXISTS idx_curated_relationship_pair ON curated_relationship(from_entity_id, to_entity_id);
CREATE INDEX IF NOT EXISTS idx_curated_relationship_status ON curated_relationship(relation_status);
