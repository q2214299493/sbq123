"""Synthetic local installed-artifact smoke; SOFTWARE_ENVIRONMENT evidence only."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json
from scripts.registry_mutations import apply_registry_batch, plan_registry_batch
from scripts.registry_schema import CURRENT_VERSION, migrate_registry
from scripts.registry_transactions import approve_plan
from scripts.runtime_resources import resource_path
from scripts.ts_strategy_engine.contract import normalize_contract


def run_smoke(root: Path) -> dict:
    profile = yaml.safe_load(resource_path("configs/true_fe110_production.yaml").read_text(encoding="utf-8"))
    assert isinstance(profile, dict) and profile
    contract = normalize_contract({
        "reaction_id": "synthetic_release", "reaction_family": "co_dissociation",
        "reactant_id": "co", "product_id": "c_o", "index_base": 0,
        "atom_map": [[0, 0], [1, 1]], "reaction_atoms": [0, 1],
        "broken_bonds": [[0, 1]], "formed_bonds": [], "site_changes": [],
        "compatibility": {"material": "fixture", "surface": "fixture", "branch": "fixture",
                          "slab_model": "fixture", "xc": "fixture", "potcar_family": "fixture",
                          "encut_ev": 400, "kmesh": [1, 1, 1], "magnetic_state": "fixture", "coverage": "fixture"},
        "endpoints": {name: {"calculation_id": name, "structure_file_id": name, "static_result_id": name}
                      for name in ("initial", "final")},
    })
    evidence = root / "synthetic_contract.json"
    write_json(evidence, contract)
    assert normalize_contract(load_json_object(evidence)) == contract
    database = root / "synthetic_registry.sqlite3"
    assert migrate_registry(database) == CURRENT_VERSION
    batch = {"schema_version": 1, "document_kind": "calculation_registry_batch",
             "batch_id": "release-smoke", "created_at": "2026-09-09T00:00:00Z",
             "reviewer": "synthetic-release-test", "reason": "software integration only",
             "rows": {
                 "calculations": [{"calculation_id": "smoke", "module": "release_test", "purpose": "synthetic",
                                   "workflow_status": "registered", "created_at": "2026-09-09T00:00:00Z"}],
                 "files": [{"file_id": "smoke-contract", "calculation_id": "smoke", "role": "input",
                            "filename": evidence.name, "local_path": str(evidence), "storage_mode": "test",
                            "existence_status": "confirmed", "sha256": sha256_file(evidence)}],
             }}
    plan = plan_registry_batch(database, batch)
    approval = approve_plan(plan, reviewer=batch["reviewer"], reviewed_at="2026-09-09T00:00:00Z")
    receipt = apply_registry_batch(database, batch, plan=plan, approval=approval, confirmed_sha256=plan["plan_sha256"])
    repeated = apply_registry_batch(database, batch, plan=plan, approval=approval, confirmed_sha256=plan["plan_sha256"])
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT sha256 FROM files WHERE file_id='smoke-contract'").fetchone()[0] == sha256_file(evidence)
        assert connection.execute("SELECT count(*) FROM results").fetchone()[0] == 0
    assert receipt["inserted"] == 2 and repeated["already_applied"]
    return {"evidence_kind": "SOFTWARE_ENVIRONMENT", "status": "PASS", "schema_version": CURRENT_VERSION,
            "contract_sha256": contract["contract_sha256"], "inserted": receipt["inserted"],
            "idempotent": True, "scientific_acceptance": False, "external_actions": 0}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    with TemporaryDirectory(prefix="sbq-release-smoke-") as directory:
        result = run_smoke(Path(directory))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
