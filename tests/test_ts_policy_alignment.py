"""Planner choices are metadata from the owning gate, never job authorization."""
import copy
from pathlib import Path

import pytest
import yaml

from scripts.execution_backends import load_execution_backends
from scripts.ts_strategy_engine import strategy
from scripts.ts_strategy_engine.dimer_gate_common import load_policy
from scripts.ts_strategy_engine.fingerprint import rank_templates
from tests.test_ts_strategy_engine import fingerprint, successful_record

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("family", ["co_dissociation", "c_o_cleavage", "hydrogen_transfer", "c_c_coupling", "co_insertion"])
def test_all_family_plans_follow_installed_dimer_policy(family):
    config = yaml.safe_load((ROOT / "configs/ts_strategy_engine/families.yaml").read_text())
    query = {**fingerprint(), "reaction_family": family}
    plan = strategy.compose_strategy(query, [], config)
    assert plan["neb_settings"]["candidate_methods"] == load_policy()["eligibility"]["parent_methods"]
    assert plan["automatic_submission"] is False
    assert plan["requires_user_confirmation"] is True
    assert "ALLOWED_ACTIONS" not in plan
    assert all("vasp_candidate_methods" not in rule for rule in config["priority_families"].values())


@pytest.mark.parametrize("reviewed_path_supported", [False, True])
def test_old_templates_follow_current_policy_without_mutating_history(monkeypatch, reviewed_path_supported):
    methods = ["ordinary_neb", "ci_neb", "gpu_ml_neb_vasp_validated_triad"]
    if reviewed_path_supported:
        methods.append("gpu_ml_neb_reviewed_path")
    monkeypatch.setattr(strategy, "load_dimer_policy", lambda: {"eligibility": {"parent_methods": methods}})
    template = successful_record()
    template["evidence_valid"] = True
    template["neb_settings"]["candidate_methods"] = ["ci_neb", "obsolete_method"]
    before = copy.deepcopy(template)
    ranked = rank_templates(fingerprint(), [template])
    config = yaml.safe_load((ROOT / "configs/ts_strategy_engine/families.yaml").read_text())
    plan = strategy.compose_strategy(fingerprint(), ranked, config)
    assert plan["strategy_source"] == "template_transfer"
    assert set(plan["neb_settings"]["candidate_methods"]) == set(methods)
    assert plan["neb_settings"]["candidate_methods"][0] == "ci_neb"
    assert template == before


@pytest.mark.parametrize("key,value,message", [
    ("neb_bidirectional_connectivity_policy", "optional", "ordinary NEB"),
    ("ci_neb_grade_a_requires_bidirectional_connectivity", True, "CI-NEB Grade A"),
    ("ci_neb_bidirectional_connectivity_role", "required", "CI-NEB connectivity"),
])
def test_backend_loader_rejects_source_method_policy_drift(tmp_path, key, value, message):
    config = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))
    config["scientific_rules"][key] = value
    path = tmp_path / "backends.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_execution_backends(path)
