-- REVIEW-ONLY destructive rollback. Direct execution is prohibited.
-- rollback_empty_ts_endpoint_migration() permits this only for an empty table
-- after an exact explicit confirmation. Non-empty rollback remains prohibited.
DROP INDEX IF EXISTS idx_ts_endpoint_reaction;
DROP TABLE IF EXISTS ts_endpoint_records;
DELETE FROM schema_metadata
WHERE key = 'ts_endpoint_schema_version';
