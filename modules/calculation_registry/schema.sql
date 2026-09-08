PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_metadata (key, value)
VALUES ('schema_version', '8');

UPDATE schema_metadata SET value = '8' WHERE key = 'schema_version';

CREATE TABLE IF NOT EXISTS ts_strategy_events (
    event_type TEXT NOT NULL CHECK (event_type IN ('variant', 'attempt', 'outcome')),
    entity_id TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    payload_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (event_type, entity_id)
);

CREATE TABLE IF NOT EXISTS calculations (
    calculation_id TEXT PRIMARY KEY,
    module TEXT NOT NULL,
    purpose TEXT NOT NULL,
    scientific_system TEXT,
    parent_calculation_id TEXT REFERENCES calculations(calculation_id),
    workflow_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    source_record TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS jobs (
    job_record_id TEXT PRIMARY KEY,
    calculation_id TEXT NOT NULL REFERENCES calculations(calculation_id),
    scheduler_job_id TEXT,
    scheduler TEXT NOT NULL,
    server_alias TEXT NOT NULL,
    queue TEXT,
    remote_directory TEXT NOT NULL,
    submit_script TEXT,
    submitted_at TEXT,
    started_at TEXT,
    finished_at TEXT,
    UNIQUE (server_alias, scheduler_job_id)
);

CREATE TABLE IF NOT EXISTS job_status_history (
    status_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_record_id TEXT NOT NULL REFERENCES jobs(job_record_id),
    scheduler_status TEXT NOT NULL,
    scientific_status TEXT NOT NULL DEFAULT 'Not assessed',
    checked_at TEXT NOT NULL,
    source_command TEXT,
    source_text TEXT,
    reviewer TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    calculation_id TEXT NOT NULL REFERENCES calculations(calculation_id),
    job_record_id TEXT REFERENCES jobs(job_record_id),
    role TEXT NOT NULL,
    filename TEXT NOT NULL,
    local_path TEXT,
    remote_path TEXT,
    storage_mode TEXT NOT NULL,
    byte_size INTEGER,
    modified_at TEXT,
    sha256 TEXT,
    existence_status TEXT NOT NULL,
    license_or_sensitivity TEXT,
    source_file_id TEXT REFERENCES files(file_id),
    notes TEXT
);

CREATE TABLE IF NOT EXISTS results (
    result_id TEXT PRIMARY KEY,
    calculation_id TEXT NOT NULL REFERENCES calculations(calculation_id),
    result_name TEXT NOT NULL,
    numeric_value REAL,
    text_value TEXT,
    unit TEXT,
    temperature_k REAL,
    pressure_pa REAL,
    reference_convention TEXT,
    source_file_id TEXT REFERENCES files(file_id),
    source_locator TEXT,
    extraction_method TEXT,
    validation_status TEXT NOT NULL,
    uncertainty_text TEXT,
    created_at TEXT NOT NULL,
    notes TEXT,
    CHECK (numeric_value IS NOT NULL OR text_value IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS reviews (
    review_id TEXT PRIMARY KEY,
    calculation_id TEXT NOT NULL REFERENCES calculations(calculation_id),
    review_type TEXT NOT NULL,
    decision TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    evidence TEXT,
    reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS calculation_workflow_status_history (
    status_change_id TEXT PRIMARY KEY,
    calculation_id TEXT NOT NULL REFERENCES calculations(calculation_id),
    previous_workflow_status TEXT NOT NULL,
    new_workflow_status TEXT NOT NULL,
    changed_at TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reason TEXT NOT NULL,
    CHECK (previous_workflow_status != new_workflow_status)
);

CREATE TABLE IF NOT EXISTS ts_validations (
    ts_validation_id TEXT PRIMARY KEY,
    calculation_id TEXT NOT NULL REFERENCES calculations(calculation_id),
    source_saddle_calculation_id TEXT NOT NULL REFERENCES calculations(calculation_id),
    source_method TEXT NOT NULL,
    source_job_record_id TEXT REFERENCES jobs(job_record_id),
    frequency_output_file_id TEXT NOT NULL REFERENCES files(file_id),
    positive_displacement_file_id TEXT REFERENCES files(file_id),
    negative_displacement_file_id TEXT REFERENCES files(file_id),
    connectivity_report_file_id TEXT REFERENCES files(file_id),
    positive_connectivity_job_record_id TEXT REFERENCES jobs(job_record_id),
    negative_connectivity_job_record_id TEXT REFERENCES jobs(job_record_id),
    connectivity_report_sha256 TEXT,
    contract_sha256 TEXT NOT NULL,
    atom_map_sha256 TEXT NOT NULL,
    compatibility_fingerprint TEXT NOT NULL,
    imaginary_frequency_count INTEGER,
    imaginary_frequencies_cm1 TEXT,
    principal_mode_assignment TEXT,
    soft_mode_assessment TEXT,
    geometry_status TEXT,
    connects_to_is INTEGER,
    connects_to_fs INTEGER,
    grade TEXT NOT NULL,
    kinetic_eligible INTEGER NOT NULL DEFAULT 0,
    reviewed_at TEXT,
    reviewer TEXT,
    notes TEXT,
    CHECK (grade IN ('A', 'B', 'C', 'Ungraded')),
    CHECK (kinetic_eligible IN (0, 1)),
    CHECK (kinetic_eligible = 0 OR grade = 'A')
);

CREATE TABLE IF NOT EXISTS calculation_compatibility (
    calculation_id TEXT PRIMARY KEY REFERENCES calculations(calculation_id),
    compatibility_fingerprint TEXT NOT NULL,
    compatibility_json TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reviewed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ts_barriers (
    barrier_set_id TEXT PRIMARY KEY,
    reaction_id TEXT NOT NULL,
    source_calculation_id TEXT NOT NULL REFERENCES calculations(calculation_id),
    ts_validation_id TEXT NOT NULL REFERENCES ts_validations(ts_validation_id),
    initial_result_id TEXT NOT NULL REFERENCES results(result_id),
    ts_result_id TEXT NOT NULL REFERENCES results(result_id),
    final_result_id TEXT NOT NULL REFERENCES results(result_id),
    compatibility_fingerprint TEXT NOT NULL,
    energy_convention TEXT NOT NULL,
    forward_barrier_ev REAL NOT NULL,
    reverse_barrier_ev REAL NOT NULL,
    reaction_energy_ev REAL NOT NULL,
    validation_status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    notes TEXT,
    CHECK (validation_status IN ('accepted', 'rejected')),
    UNIQUE (reaction_id, initial_result_id, ts_result_id, final_result_id)
);

CREATE TABLE IF NOT EXISTS ts_strategy_templates (
    template_id TEXT PRIMARY KEY,
    reaction_family TEXT NOT NULL,
    fingerprint_json TEXT NOT NULL,
    waypoint_strategy_json TEXT NOT NULL,
    interpolation_strategy TEXT NOT NULL,
    neb_settings_json TEXT NOT NULL,
    dimer_usage_json TEXT NOT NULL,
    ts_structure_file_id TEXT REFERENCES files(file_id),
    ts_validation_id TEXT REFERENCES ts_validations(ts_validation_id),
    barrier_set_id TEXT REFERENCES ts_barriers(barrier_set_id),
    barrier_ev REAL,
    convergence_history_json TEXT NOT NULL,
    failure_cases_json TEXT NOT NULL,
    correction_strategy TEXT,
    outcome TEXT NOT NULL,
    validation_grade TEXT NOT NULL,
    source_calculation_id TEXT NOT NULL REFERENCES calculations(calculation_id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (outcome IN ('success', 'failure')),
    CHECK (validation_grade IN ('A', 'B', 'C', 'Ungraded')),
    CHECK (outcome != 'success' OR validation_grade = 'A'),
    CHECK (outcome != 'success' OR (
        ts_structure_file_id IS NOT NULL
        AND ts_validation_id IS NOT NULL
        AND barrier_set_id IS NOT NULL
        AND barrier_ev IS NOT NULL
    )),
    CHECK (outcome != 'failure' OR correction_strategy IS NOT NULL)
);

-- A receipt is written only after a hash-bound, reviewer-approved registry
-- record has been appended to a workbook by the controlled exporter. The
-- registry remains the scientific authority; the workbook is a reviewed view.
CREATE TABLE IF NOT EXISTS excel_promotions (
    promotion_id TEXT PRIMARY KEY,
    promotion_kind TEXT NOT NULL CHECK (promotion_kind IN ('adsorption', 'barrier')),
    registry_id TEXT NOT NULL,
    calculation_id TEXT REFERENCES calculations(calculation_id),
    workbook_path TEXT NOT NULL,
    worksheet_name TEXT NOT NULL,
    row_number INTEGER NOT NULL CHECK (row_number > 1),
    workbook_sha256_before TEXT NOT NULL,
    workbook_sha256_after TEXT NOT NULL,
    written_values_sha256 TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    reviewed_at TEXT NOT NULL,
    receipt_path TEXT NOT NULL,
    request_sha256 TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    notes TEXT,
    UNIQUE (promotion_kind, registry_id),
    UNIQUE (workbook_path, worksheet_name, row_number)
);

CREATE INDEX IF NOT EXISTS idx_jobs_calculation
ON jobs(calculation_id);

CREATE INDEX IF NOT EXISTS idx_status_job_time
ON job_status_history(job_record_id, checked_at);

CREATE INDEX IF NOT EXISTS idx_files_calculation_role
ON files(calculation_id, role);

CREATE INDEX IF NOT EXISTS idx_results_calculation_name
ON results(calculation_id, result_name);

CREATE INDEX IF NOT EXISTS idx_calculation_workflow_status_history
ON calculation_workflow_status_history(calculation_id, changed_at);

CREATE INDEX IF NOT EXISTS idx_ts_strategy_family
ON ts_strategy_templates(reaction_family, outcome, validation_grade);

CREATE UNIQUE INDEX IF NOT EXISTS idx_ts_strategy_unique_experience
ON ts_strategy_templates(source_calculation_id, fingerprint_json, outcome);

CREATE INDEX IF NOT EXISTS idx_ts_barriers_reaction
ON ts_barriers(reaction_id, validation_status);

CREATE INDEX IF NOT EXISTS idx_excel_promotions_registry
ON excel_promotions(promotion_kind, registry_id);
