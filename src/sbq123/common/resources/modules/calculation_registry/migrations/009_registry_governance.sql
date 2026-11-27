CREATE TABLE registry_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE TABLE registry_applications (
    plan_sha256 TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL UNIQUE,
    batch_sha256 TEXT NOT NULL,
    receipt_json TEXT NOT NULL
);
CREATE TABLE compatibility_revisions (
    revision_id TEXT PRIMARY KEY,
    compatibility_json TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    supersedes_revision_id TEXT REFERENCES compatibility_revisions(revision_id)
);
CREATE TABLE calculation_compatibility_revisions (
    calculation_id TEXT PRIMARY KEY REFERENCES calculations(calculation_id),
    revision_id TEXT NOT NULL REFERENCES compatibility_revisions(revision_id)
);
INSERT OR IGNORE INTO compatibility_revisions
SELECT compatibility_fingerprint, compatibility_json, reviewer, reviewed_at, NULL
FROM calculation_compatibility ORDER BY calculation_id;
INSERT INTO calculation_compatibility_revisions
SELECT calculation_id, compatibility_fingerprint FROM calculation_compatibility;
CREATE TRIGGER bind_compatibility_revision AFTER INSERT ON calculation_compatibility
BEGIN
    INSERT INTO compatibility_revisions
    SELECT NEW.compatibility_fingerprint, NEW.compatibility_json, NEW.reviewer, NEW.reviewed_at, NULL
    WHERE NOT EXISTS (SELECT 1 FROM compatibility_revisions WHERE revision_id=NEW.compatibility_fingerprint);
    INSERT INTO calculation_compatibility_revisions VALUES (NEW.calculation_id, NEW.compatibility_fingerprint);
END;
CREATE TRIGGER immutable_registry_events_update BEFORE UPDATE ON registry_events
BEGIN SELECT RAISE(ABORT, 'immutable registry_events'); END;
CREATE TRIGGER immutable_registry_events_delete BEFORE DELETE ON registry_events
BEGIN SELECT RAISE(ABORT, 'immutable registry_events'); END;
CREATE TRIGGER immutable_registry_applications_update BEFORE UPDATE ON registry_applications
BEGIN SELECT RAISE(ABORT, 'immutable registry_applications'); END;
CREATE TRIGGER immutable_registry_applications_delete BEFORE DELETE ON registry_applications
BEGIN SELECT RAISE(ABORT, 'immutable registry_applications'); END;
CREATE TRIGGER immutable_compatibility_revisions_update BEFORE UPDATE ON compatibility_revisions
BEGIN SELECT RAISE(ABORT, 'immutable compatibility_revisions'); END;
CREATE TRIGGER immutable_compatibility_revisions_delete BEFORE DELETE ON compatibility_revisions
BEGIN SELECT RAISE(ABORT, 'immutable compatibility_revisions'); END;
CREATE TRIGGER immutable_calculation_compatibility_revisions_update BEFORE UPDATE ON calculation_compatibility_revisions
BEGIN SELECT RAISE(ABORT, 'immutable calculation_compatibility_revisions'); END;
CREATE TRIGGER immutable_calculation_compatibility_revisions_delete BEFORE DELETE ON calculation_compatibility_revisions
BEGIN SELECT RAISE(ABORT, 'immutable calculation_compatibility_revisions'); END;
CREATE TRIGGER immutable_calculation_compatibility_update BEFORE UPDATE ON calculation_compatibility
BEGIN SELECT RAISE(ABORT, 'immutable calculation_compatibility'); END;
CREATE TRIGGER immutable_calculation_compatibility_delete BEFORE DELETE ON calculation_compatibility
BEGIN SELECT RAISE(ABORT, 'immutable calculation_compatibility'); END;
CREATE TRIGGER immutable_job_status_history_update BEFORE UPDATE ON job_status_history
BEGIN SELECT RAISE(ABORT, 'immutable job_status_history'); END;
CREATE TRIGGER immutable_job_status_history_delete BEFORE DELETE ON job_status_history
BEGIN SELECT RAISE(ABORT, 'immutable job_status_history'); END;
CREATE TRIGGER immutable_calculation_workflow_status_history_update BEFORE UPDATE ON calculation_workflow_status_history
BEGIN SELECT RAISE(ABORT, 'immutable calculation_workflow_status_history'); END;
CREATE TRIGGER immutable_calculation_workflow_status_history_delete BEFORE DELETE ON calculation_workflow_status_history
BEGIN SELECT RAISE(ABORT, 'immutable calculation_workflow_status_history'); END;
CREATE TRIGGER immutable_ts_strategy_events_update BEFORE UPDATE ON ts_strategy_events
BEGIN SELECT RAISE(ABORT, 'immutable ts_strategy_events'); END;
CREATE TRIGGER immutable_ts_strategy_events_delete BEFORE DELETE ON ts_strategy_events
BEGIN SELECT RAISE(ABORT, 'immutable ts_strategy_events'); END;
UPDATE schema_metadata SET value='9' WHERE key='schema_version';
CREATE TRIGGER immutable_results_update BEFORE UPDATE ON results
BEGIN SELECT RAISE(ABORT, 'immutable results'); END;
CREATE TRIGGER immutable_results_delete BEFORE DELETE ON results
BEGIN SELECT RAISE(ABORT, 'immutable results'); END;
CREATE TRIGGER immutable_files_update BEFORE UPDATE ON files
BEGIN SELECT RAISE(ABORT, 'immutable files'); END;
CREATE TRIGGER immutable_files_delete BEFORE DELETE ON files
BEGIN SELECT RAISE(ABORT, 'immutable files'); END;
CREATE TRIGGER immutable_reviews_update BEFORE UPDATE ON reviews
BEGIN SELECT RAISE(ABORT, 'immutable reviews'); END;
CREATE TRIGGER immutable_reviews_delete BEFORE DELETE ON reviews
BEGIN SELECT RAISE(ABORT, 'immutable reviews'); END;
CREATE TRIGGER immutable_ts_validations_update BEFORE UPDATE ON ts_validations
BEGIN SELECT RAISE(ABORT, 'immutable ts_validations'); END;
CREATE TRIGGER immutable_ts_validations_delete BEFORE DELETE ON ts_validations
BEGIN SELECT RAISE(ABORT, 'immutable ts_validations'); END;
CREATE TRIGGER immutable_ts_barriers_update BEFORE UPDATE ON ts_barriers
BEGIN SELECT RAISE(ABORT, 'immutable ts_barriers'); END;
CREATE TRIGGER immutable_ts_barriers_delete BEFORE DELETE ON ts_barriers
BEGIN SELECT RAISE(ABORT, 'immutable ts_barriers'); END;
CREATE TRIGGER immutable_ts_strategy_templates_update BEFORE UPDATE ON ts_strategy_templates
BEGIN SELECT RAISE(ABORT, 'immutable ts_strategy_templates'); END;
CREATE TRIGGER immutable_ts_strategy_templates_delete BEFORE DELETE ON ts_strategy_templates
BEGIN SELECT RAISE(ABORT, 'immutable ts_strategy_templates'); END;
CREATE TRIGGER immutable_excel_promotions_update BEFORE UPDATE ON excel_promotions
BEGIN SELECT RAISE(ABORT, 'immutable excel_promotions'); END;
CREATE TRIGGER immutable_excel_promotions_delete BEFORE DELETE ON excel_promotions
BEGIN SELECT RAISE(ABORT, 'immutable excel_promotions'); END;
CREATE VIEW job_current_state AS
SELECT h.* FROM job_status_history AS h
WHERE h.status_event_id = (SELECT MAX(latest.status_event_id) FROM job_status_history AS latest
                          WHERE latest.job_record_id=h.job_record_id);
CREATE TABLE job_recovery_events (
    event_id TEXT PRIMARY KEY,
    status_event_id INTEGER NOT NULL UNIQUE REFERENCES job_status_history(status_event_id),
    timestamp TEXT NOT NULL,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL
);
CREATE TRIGGER immutable_job_recovery_events_update BEFORE UPDATE ON job_recovery_events
BEGIN SELECT RAISE(ABORT, 'immutable job_recovery_events'); END;
CREATE TRIGGER immutable_job_recovery_events_delete BEFORE DELETE ON job_recovery_events
BEGIN SELECT RAISE(ABORT, 'immutable job_recovery_events'); END;
CREATE TRIGGER immutable_registry_events_replace BEFORE INSERT ON registry_events
WHEN EXISTS (SELECT 1 FROM registry_events WHERE "event_id" IS NEW."event_id" AND ("event_id" IS NOT NEW."event_id" OR "event_type" IS NOT NEW."event_type" OR "entity_id" IS NOT NEW."entity_id" OR "payload_json" IS NOT NEW."payload_json" OR "occurred_at" IS NOT NEW."occurred_at" OR "actor" IS NOT NEW."actor" OR "reason" IS NOT NEW."reason"))
BEGIN SELECT RAISE(ABORT, 'immutable registry_events'); END;
CREATE TRIGGER immutable_registry_applications_replace BEFORE INSERT ON registry_applications
WHEN EXISTS (SELECT 1 FROM registry_applications WHERE "plan_sha256" IS NEW."plan_sha256" AND ("plan_sha256" IS NOT NEW."plan_sha256" OR "batch_id" IS NOT NEW."batch_id" OR "batch_sha256" IS NOT NEW."batch_sha256" OR "receipt_json" IS NOT NEW."receipt_json"))
BEGIN SELECT RAISE(ABORT, 'immutable registry_applications'); END;
CREATE TRIGGER immutable_compatibility_revisions_replace BEFORE INSERT ON compatibility_revisions
WHEN EXISTS (SELECT 1 FROM compatibility_revisions WHERE "revision_id" IS NEW."revision_id" AND ("revision_id" IS NOT NEW."revision_id" OR "compatibility_json" IS NOT NEW."compatibility_json" OR "reviewer" IS NOT NEW."reviewer" OR "reviewed_at" IS NOT NEW."reviewed_at" OR "supersedes_revision_id" IS NOT NEW."supersedes_revision_id"))
BEGIN SELECT RAISE(ABORT, 'immutable compatibility_revisions'); END;
CREATE TRIGGER immutable_calculation_compatibility_revisions_replace BEFORE INSERT ON calculation_compatibility_revisions
WHEN EXISTS (SELECT 1 FROM calculation_compatibility_revisions WHERE "calculation_id" IS NEW."calculation_id" AND ("calculation_id" IS NOT NEW."calculation_id" OR "revision_id" IS NOT NEW."revision_id"))
BEGIN SELECT RAISE(ABORT, 'immutable calculation_compatibility_revisions'); END;
CREATE TRIGGER immutable_calculation_compatibility_replace BEFORE INSERT ON calculation_compatibility
WHEN EXISTS (SELECT 1 FROM calculation_compatibility WHERE "calculation_id" IS NEW."calculation_id" AND ("calculation_id" IS NOT NEW."calculation_id" OR "compatibility_fingerprint" IS NOT NEW."compatibility_fingerprint" OR "compatibility_json" IS NOT NEW."compatibility_json" OR "reviewer" IS NOT NEW."reviewer" OR "reviewed_at" IS NOT NEW."reviewed_at"))
BEGIN SELECT RAISE(ABORT, 'immutable calculation_compatibility'); END;
CREATE TRIGGER immutable_job_status_history_replace BEFORE INSERT ON job_status_history
WHEN EXISTS (SELECT 1 FROM job_status_history WHERE "status_event_id" IS NEW."status_event_id" AND ("status_event_id" IS NOT NEW."status_event_id" OR "job_record_id" IS NOT NEW."job_record_id" OR "scheduler_status" IS NOT NEW."scheduler_status" OR "scientific_status" IS NOT NEW."scientific_status" OR "checked_at" IS NOT NEW."checked_at" OR "source_command" IS NOT NEW."source_command" OR "source_text" IS NOT NEW."source_text" OR "reviewer" IS NOT NEW."reviewer" OR "notes" IS NOT NEW."notes"))
BEGIN SELECT RAISE(ABORT, 'immutable job_status_history'); END;
CREATE TRIGGER immutable_calculation_workflow_status_history_replace BEFORE INSERT ON calculation_workflow_status_history
WHEN EXISTS (SELECT 1 FROM calculation_workflow_status_history WHERE "status_change_id" IS NEW."status_change_id" AND ("status_change_id" IS NOT NEW."status_change_id" OR "calculation_id" IS NOT NEW."calculation_id" OR "previous_workflow_status" IS NOT NEW."previous_workflow_status" OR "new_workflow_status" IS NOT NEW."new_workflow_status" OR "changed_at" IS NOT NEW."changed_at" OR "reviewer" IS NOT NEW."reviewer" OR "reason" IS NOT NEW."reason"))
BEGIN SELECT RAISE(ABORT, 'immutable calculation_workflow_status_history'); END;
CREATE TRIGGER immutable_ts_strategy_events_replace BEFORE INSERT ON ts_strategy_events
WHEN EXISTS (SELECT 1 FROM ts_strategy_events WHERE "event_type" IS NEW."event_type" AND "entity_id" IS NEW."entity_id" AND ("event_type" IS NOT NEW."event_type" OR "entity_id" IS NOT NEW."entity_id" OR "payload_json" IS NOT NEW."payload_json" OR "payload_sha256" IS NOT NEW."payload_sha256" OR "created_at" IS NOT NEW."created_at"))
BEGIN SELECT RAISE(ABORT, 'immutable ts_strategy_events'); END;
CREATE TRIGGER immutable_results_replace BEFORE INSERT ON results
WHEN EXISTS (SELECT 1 FROM results WHERE "result_id" IS NEW."result_id" AND ("result_id" IS NOT NEW."result_id" OR "calculation_id" IS NOT NEW."calculation_id" OR "result_name" IS NOT NEW."result_name" OR "numeric_value" IS NOT NEW."numeric_value" OR "text_value" IS NOT NEW."text_value" OR "unit" IS NOT NEW."unit" OR "temperature_k" IS NOT NEW."temperature_k" OR "pressure_pa" IS NOT NEW."pressure_pa" OR "reference_convention" IS NOT NEW."reference_convention" OR "source_file_id" IS NOT NEW."source_file_id" OR "source_locator" IS NOT NEW."source_locator" OR "extraction_method" IS NOT NEW."extraction_method" OR "validation_status" IS NOT NEW."validation_status" OR "uncertainty_text" IS NOT NEW."uncertainty_text" OR "created_at" IS NOT NEW."created_at" OR "notes" IS NOT NEW."notes"))
BEGIN SELECT RAISE(ABORT, 'immutable results'); END;
CREATE TRIGGER immutable_files_replace BEFORE INSERT ON files
WHEN EXISTS (SELECT 1 FROM files WHERE "file_id" IS NEW."file_id" AND ("file_id" IS NOT NEW."file_id" OR "calculation_id" IS NOT NEW."calculation_id" OR "job_record_id" IS NOT NEW."job_record_id" OR "role" IS NOT NEW."role" OR "filename" IS NOT NEW."filename" OR "local_path" IS NOT NEW."local_path" OR "remote_path" IS NOT NEW."remote_path" OR "storage_mode" IS NOT NEW."storage_mode" OR "byte_size" IS NOT NEW."byte_size" OR "modified_at" IS NOT NEW."modified_at" OR "sha256" IS NOT NEW."sha256" OR "existence_status" IS NOT NEW."existence_status" OR "license_or_sensitivity" IS NOT NEW."license_or_sensitivity" OR "source_file_id" IS NOT NEW."source_file_id" OR "notes" IS NOT NEW."notes"))
BEGIN SELECT RAISE(ABORT, 'immutable files'); END;
CREATE TRIGGER immutable_reviews_replace BEFORE INSERT ON reviews
WHEN EXISTS (SELECT 1 FROM reviews WHERE "review_id" IS NEW."review_id" AND ("review_id" IS NOT NEW."review_id" OR "calculation_id" IS NOT NEW."calculation_id" OR "review_type" IS NOT NEW."review_type" OR "decision" IS NOT NEW."decision" OR "reviewer" IS NOT NEW."reviewer" OR "reviewed_at" IS NOT NEW."reviewed_at" OR "evidence" IS NOT NEW."evidence" OR "reason" IS NOT NEW."reason"))
BEGIN SELECT RAISE(ABORT, 'immutable reviews'); END;
CREATE TRIGGER immutable_ts_validations_replace BEFORE INSERT ON ts_validations
WHEN EXISTS (SELECT 1 FROM ts_validations WHERE "ts_validation_id" IS NEW."ts_validation_id" AND ("ts_validation_id" IS NOT NEW."ts_validation_id" OR "calculation_id" IS NOT NEW."calculation_id" OR "source_saddle_calculation_id" IS NOT NEW."source_saddle_calculation_id" OR "source_method" IS NOT NEW."source_method" OR "source_job_record_id" IS NOT NEW."source_job_record_id" OR "frequency_output_file_id" IS NOT NEW."frequency_output_file_id" OR "positive_displacement_file_id" IS NOT NEW."positive_displacement_file_id" OR "negative_displacement_file_id" IS NOT NEW."negative_displacement_file_id" OR "connectivity_report_file_id" IS NOT NEW."connectivity_report_file_id" OR "positive_connectivity_job_record_id" IS NOT NEW."positive_connectivity_job_record_id" OR "negative_connectivity_job_record_id" IS NOT NEW."negative_connectivity_job_record_id" OR "connectivity_report_sha256" IS NOT NEW."connectivity_report_sha256" OR "contract_sha256" IS NOT NEW."contract_sha256" OR "atom_map_sha256" IS NOT NEW."atom_map_sha256" OR "compatibility_fingerprint" IS NOT NEW."compatibility_fingerprint" OR "imaginary_frequency_count" IS NOT NEW."imaginary_frequency_count" OR "imaginary_frequencies_cm1" IS NOT NEW."imaginary_frequencies_cm1" OR "principal_mode_assignment" IS NOT NEW."principal_mode_assignment" OR "soft_mode_assessment" IS NOT NEW."soft_mode_assessment" OR "geometry_status" IS NOT NEW."geometry_status" OR "connects_to_is" IS NOT NEW."connects_to_is" OR "connects_to_fs" IS NOT NEW."connects_to_fs" OR "grade" IS NOT NEW."grade" OR "kinetic_eligible" IS NOT NEW."kinetic_eligible" OR "reviewed_at" IS NOT NEW."reviewed_at" OR "reviewer" IS NOT NEW."reviewer" OR "notes" IS NOT NEW."notes"))
BEGIN SELECT RAISE(ABORT, 'immutable ts_validations'); END;
CREATE TRIGGER immutable_ts_barriers_replace BEFORE INSERT ON ts_barriers
WHEN EXISTS (SELECT 1 FROM ts_barriers WHERE "barrier_set_id" IS NEW."barrier_set_id" AND ("barrier_set_id" IS NOT NEW."barrier_set_id" OR "reaction_id" IS NOT NEW."reaction_id" OR "source_calculation_id" IS NOT NEW."source_calculation_id" OR "ts_validation_id" IS NOT NEW."ts_validation_id" OR "initial_result_id" IS NOT NEW."initial_result_id" OR "ts_result_id" IS NOT NEW."ts_result_id" OR "final_result_id" IS NOT NEW."final_result_id" OR "compatibility_fingerprint" IS NOT NEW."compatibility_fingerprint" OR "energy_convention" IS NOT NEW."energy_convention" OR "forward_barrier_ev" IS NOT NEW."forward_barrier_ev" OR "reverse_barrier_ev" IS NOT NEW."reverse_barrier_ev" OR "reaction_energy_ev" IS NOT NEW."reaction_energy_ev" OR "validation_status" IS NOT NEW."validation_status" OR "created_at" IS NOT NEW."created_at" OR "notes" IS NOT NEW."notes"))
BEGIN SELECT RAISE(ABORT, 'immutable ts_barriers'); END;
CREATE TRIGGER immutable_ts_strategy_templates_replace BEFORE INSERT ON ts_strategy_templates
WHEN EXISTS (SELECT 1 FROM ts_strategy_templates WHERE "template_id" IS NEW."template_id" AND ("template_id" IS NOT NEW."template_id" OR "reaction_family" IS NOT NEW."reaction_family" OR "fingerprint_json" IS NOT NEW."fingerprint_json" OR "waypoint_strategy_json" IS NOT NEW."waypoint_strategy_json" OR "interpolation_strategy" IS NOT NEW."interpolation_strategy" OR "neb_settings_json" IS NOT NEW."neb_settings_json" OR "dimer_usage_json" IS NOT NEW."dimer_usage_json" OR "ts_structure_file_id" IS NOT NEW."ts_structure_file_id" OR "ts_validation_id" IS NOT NEW."ts_validation_id" OR "barrier_set_id" IS NOT NEW."barrier_set_id" OR "barrier_ev" IS NOT NEW."barrier_ev" OR "convergence_history_json" IS NOT NEW."convergence_history_json" OR "failure_cases_json" IS NOT NEW."failure_cases_json" OR "correction_strategy" IS NOT NEW."correction_strategy" OR "outcome" IS NOT NEW."outcome" OR "validation_grade" IS NOT NEW."validation_grade" OR "source_calculation_id" IS NOT NEW."source_calculation_id" OR "created_at" IS NOT NEW."created_at" OR "updated_at" IS NOT NEW."updated_at"))
BEGIN SELECT RAISE(ABORT, 'immutable ts_strategy_templates'); END;
CREATE TRIGGER immutable_excel_promotions_replace BEFORE INSERT ON excel_promotions
WHEN EXISTS (SELECT 1 FROM excel_promotions WHERE "promotion_id" IS NEW."promotion_id" AND ("promotion_id" IS NOT NEW."promotion_id" OR "promotion_kind" IS NOT NEW."promotion_kind" OR "registry_id" IS NOT NEW."registry_id" OR "calculation_id" IS NOT NEW."calculation_id" OR "workbook_path" IS NOT NEW."workbook_path" OR "worksheet_name" IS NOT NEW."worksheet_name" OR "row_number" IS NOT NEW."row_number" OR "workbook_sha256_before" IS NOT NEW."workbook_sha256_before" OR "workbook_sha256_after" IS NOT NEW."workbook_sha256_after" OR "written_values_sha256" IS NOT NEW."written_values_sha256" OR "reviewer" IS NOT NEW."reviewer" OR "reviewed_at" IS NOT NEW."reviewed_at" OR "receipt_path" IS NOT NEW."receipt_path" OR "request_sha256" IS NOT NEW."request_sha256" OR "created_at" IS NOT NEW."created_at" OR "notes" IS NOT NEW."notes"))
BEGIN SELECT RAISE(ABORT, 'immutable excel_promotions'); END;
CREATE TRIGGER immutable_job_recovery_events_replace BEFORE INSERT ON job_recovery_events
WHEN EXISTS (SELECT 1 FROM job_recovery_events WHERE "event_id" IS NEW."event_id" AND ("event_id" IS NOT NEW."event_id" OR "status_event_id" IS NOT NEW."status_event_id" OR "timestamp" IS NOT NEW."timestamp" OR "actor" IS NOT NEW."actor" OR "reason" IS NOT NEW."reason"))
BEGIN SELECT RAISE(ABORT, 'immutable job_recovery_events'); END;
