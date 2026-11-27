-- REVIEW-ONLY extension. Do not execute this file directly.
-- Use apply_ts_endpoint_migration(), which validates any existing schema and
-- verifies the complete table, foreign-key, index, constraint, and version shape.
CREATE TABLE IF NOT EXISTS ts_endpoint_records (
    endpoint_record_id TEXT PRIMARY KEY,
    reaction_id TEXT NOT NULL,
    endpoint_role TEXT NOT NULL,
    structure_hash TEXT NOT NULL,
    endpoint_version TEXT NOT NULL,
    source_calculation_id TEXT REFERENCES calculations(calculation_id),
    stable_structure_file_id TEXT REFERENCES files(file_id),
    ts_structure_file_id TEXT REFERENCES files(file_id),
    endpoint_structure_path TEXT,
    is_same_as_stable INTEGER NOT NULL,
    validation_status TEXT NOT NULL,
    validation_json TEXT NOT NULL,
    threshold_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (endpoint_role IN ('initial', 'final')),
    CHECK (is_same_as_stable IN (0, 1)),
    CHECK (
        (is_same_as_stable = 1 AND endpoint_structure_path IS NULL)
        OR
        (is_same_as_stable = 0 AND endpoint_structure_path IS NOT NULL)
    ),
    CHECK (
        validation_status IN (
            'VALID',
            'VALID_WITH_WARNING',
            'REVIEW_REQUIRED',
            'REJECTED'
        )
    ),
    UNIQUE (reaction_id, endpoint_role, structure_hash, endpoint_version)
);

CREATE INDEX IF NOT EXISTS idx_ts_endpoint_reaction
ON ts_endpoint_records(reaction_id, endpoint_role);

INSERT OR IGNORE INTO schema_metadata (key, value)
VALUES ('ts_endpoint_schema_version', '1');

UPDATE schema_metadata
SET value = '1'
WHERE key = 'ts_endpoint_schema_version';
