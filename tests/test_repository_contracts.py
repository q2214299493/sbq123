from __future__ import annotations

import hashlib
import json
import importlib.util
import re
import tomllib
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
APPROVED_ARTIFACT_LAYOUT = {
    "final_release_baseline": (
        "blocked_migration_manifest.txt",
        "config_manifest.txt",
        "documentation_manifest.txt",
        "final_release_sha256.txt",
        "governance_manifest.txt",
        "parent_review_baseline_v2_sha256.txt",
        "production_source_manifest.txt",
        "test_manifest.txt",
    ),
    "refactor_changeset": (
        "changeset_sha256.txt",
        "tracked_changes.patch",
        "untracked_source_manifest.txt",
    ),
    "review_baseline_v2": (
        "baseline_v2_sha256.txt",
        "current_config_manifest.txt",
        "current_document_manifest.txt",
        "current_migration_manifest.txt",
        "current_source_manifest.txt",
        "current_test_manifest.txt",
        "parent_baseline_sha256.txt",
    ),
    "review_baseline_v3": (
        "baseline_v3_sha256.txt",
        "parent_v2_sha256.txt",
        "phase_2b_verified_document_manifest.txt",
        "phase_2b_verified_source_manifest.txt",
        "phase_2b_verified_test_manifest.txt",
    ),
    "source_baseline": (
        "baseline_sha256.txt",
        "formal_config_paths.txt",
        "formal_migration_paths.txt",
        "formal_source_paths.txt",
        "formal_test_paths.txt",
    ),
}


def _assert_exact_artifact_layout(artifacts_root: Path) -> None:
    assert sorted(path.name for path in artifacts_root.iterdir()) == sorted(
        APPROVED_ARTIFACT_LAYOUT
    )
    for directory, expected_files in APPROVED_ARTIFACT_LAYOUT.items():
        artifact_directory = artifacts_root / directory
        assert artifact_directory.is_dir()
        assert sorted(path.name for path in artifact_directory.iterdir()) == sorted(
            expected_files
        )


def _create_exact_artifact_layout(artifacts_root: Path) -> None:
    artifacts_root.mkdir()
    for directory, filenames in APPROVED_ARTIFACT_LAYOUT.items():
        artifact_directory = artifacts_root / directory
        artifact_directory.mkdir()
        for filename in filenames:
            (artifact_directory / filename).touch()


def test_active_contract_files_parse() -> None:
    for path in (ROOT / "configs").rglob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))


def test_optional_dependencies_follow_runtime_ownership() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    extras = project["optional-dependencies"]
    assert extras["neb"] == ["ase>=3.23,<4"]
    assert extras["visualization"] == ["matplotlib>=3.8,<4"]
    assert all(
        "matplotlib" not in path.read_text(encoding="utf-8")
        for path in (ROOT / "scripts" / "neb_agent").rglob("*.py")
    )
    renderer = ROOT / "scripts" / "adsorption" / "render_fe110_ch_h_candidates.py"
    assert "import matplotlib" in renderer.read_text(encoding="utf-8")
    for path in (ROOT / "configs").rglob("*.yaml"):
        yaml.safe_load(path.read_text(encoding="utf-8"))
    yaml.safe_load((ROOT / "skills" / "catalysis-data-retrieval" / "references" / "sources.yaml").read_text(encoding="utf-8"))


def test_aqcat25_ts_active_learning_schema_is_valid() -> None:
    schema = json.loads(
        (ROOT / "configs" / "aqcat25_ts_active_learning.schema.json").read_text(encoding="utf-8")
    )
    Draft202012Validator.check_schema(schema)


def test_skill_routing_is_the_single_owner_and_rule_source_map() -> None:
    routing = yaml.safe_load((ROOT / "configs" / "skill_routing.yaml").read_text(encoding="utf-8"))
    authority = routing["authority_contract"]

    assert authority["canonical_routing_and_ownership_file"] == "configs/skill_routing.yaml"
    for relative in authority["rule_sources"].values():
        assert (ROOT / relative).is_file(), relative
    assert routing["owners"] == {
        "external_structure_and_path_retrieval": "catalysis-data-retrieval",
        "adsorption_motif_planning": "adsmind_lite",
        "adsorption_structure_generation": "surface-adsorption-builder",
        "adsorption_result_validation": "adsorption_workflow",
        "transition_state_search": "transition_state_search",
        "calculation_registry": "calculation_registry",
    }
    assert routing["pre_calculation_adsorption_motif_gate"]["owner"] == "adsmind_lite"
    assert routing["execution_backend_contract"] == {
        "owner": "project_orchestration",
        "consumers": ["adsorption_workflow", "transition_state_search"],
        "rules": "configs/execution_backends.yaml",
        "required_for_external_acceleration": True,
        "direct_gpu_to_vasp_handoff": "forbidden",
    }
    for relative in (
        "modules/README.md",
        "modules/adsmind_lite/README.md",
        "modules/adsorption_workflow/README.md",
        "skills/vasp-catalysis-workflow/SKILL.md",
        "skills/surface-adsorption-builder/SKILL.md",
        "skills/catalysis-data-retrieval/SKILL.md",
        "skills/fe110-adsorbate-pilot-builder/SKILL.md",
        "skills/chemical-plausibility-gate/SKILL.md",
    ):
        assert "configs/skill_routing.yaml" in (ROOT / relative).read_text(encoding="utf-8")

    for relative in (
        "modules/README.md",
        "modules/adsorption_workflow/README.md",
        "modules/transition_state_search/README.md",
        "skills/vasp-catalysis-workflow/SKILL.md",
        "skills/surface-adsorption-builder/SKILL.md",
        "tasks/current_task.md",
        "docs/13_WORK_HANDOFF.md",
    ):
        assert "configs/execution_backends.yaml" in (ROOT / relative).read_text(encoding="utf-8")


def test_execution_backends_keep_gpu_and_vasp_authority_separate() -> None:
    contract = yaml.safe_load((ROOT / "configs" / "execution_backends.yaml").read_text(encoding="utf-8"))
    backends = contract["backends"]
    gpu = backends["aqcat_gpu"]
    vasp = backends["vasp"]

    assert contract["authority"]["direct_gpu_to_vasp_handoff"] == "forbidden"
    assert contract["authority"]["automatic_remote_submission"] == "forbidden"
    assert contract["authority"]["consumers"] == ["adsorption_workflow", "transition_state_search"]
    assert gpu["observed_hostname"] == "MZ73"
    assert gpu["remote_write_boundary"] == "/home/sbq/sbq"
    assert gpu["scheduler"]["accounting_storage_type"] == "accounting_storage/none"
    assert gpu["scheduler"]["required_workflow_evidence"] == "producer_exit_record"
    assert gpu["scheduler"]["producer_exit_record_is_scheduler_authority"] is False
    assert "adsorption_candidate_ml_relaxation_and_ranking" in gpu["allowed"]
    assert {"vasp_execution", "transition_state_acceptance", "external_evidence_gate_bypass"} <= set(gpu["forbidden"])
    assert vasp["ssh_alias"] == "sunboquan-codex"
    assert "vasp_static_energy_and_force" in vasp["allowed"]
    assert "vasp_adsorption_relaxation_and_final_static" in vasp["allowed"]
    assert "unreviewed_gpu_candidate_submission" in vasp["forbidden"]

    handoffs = contract["handoffs"]
    assert set(handoffs["work_to_gpu"]["workflows"]) == {"adsorption", "transition_state"}
    assert handoffs["gpu_to_work"]["workflows"]["adsorption"]["result_class"] == "predicted_adsorption_candidate_only"
    assert handoffs["gpu_to_work"]["workflows"]["transition_state"]["result_class"] == "predicted_transition_state_candidate_only"
    assert handoffs["work_to_vasp"]["gate"] == "reviewed_candidate_and_vasp_preflight_pass"
    assert set(handoffs["work_to_vasp"]["workflows"]) == {"adsorption", "transition_state"}
    assert handoffs["vasp_to_work"]["result_class"] == "calculation_evidence_pending_scientific_validation"
    assert contract["scientific_rules"]["aqcat_values_may_enter_reportable_dft_tables"] is False
    assert contract["scientific_rules"]["aqcat_may_replace_whitelist_or_literature_evidence_gate"] is False
    assert contract["scientific_rules"]["aqcat_alone_may_remove_an_evidence_required_adsorption_motif"] is False
    assert contract["scientific_rules"]["aqcat_may_prove_final_adsorption_site_or_global_minimum"] is False
    assert contract["scientific_rules"]["aqcat_ranking_requires_in_domain_calibration_status"] is True
    aqcat_contract = contract["aqcat25_contract"]
    assert aqcat_contract["schema_version"] == 2
    assert (ROOT / aqcat_contract["schema"]).is_file()
    assert (ROOT / aqcat_contract["validator"]).is_file()
    assert (ROOT / aqcat_contract["domain_gate"]).is_file()
    assert aqcat_contract["species_specific_hard_code"] == "forbidden"
    assert handoffs["work_to_gpu"]["schema_direction"] == "work_to_gpu"
    assert handoffs["gpu_to_work"]["schema_direction"] == "gpu_to_work"
    assert "producer_exit_record" in handoffs["gpu_to_work"]["required"]

    active_learning = contract["aqcat25_ts_active_learning"]
    assert active_learning["automatic_submission"] == "forbidden"
    assert active_learning["local_force_agreement_claim"] == "heuristic_finetuning_trigger_only"
    assert active_learning["active_learning_convergence_claim"] == (
        "independent_ts_domain_validation_required_not_transition_state_acceptance"
    )
    assert active_learning["vasp_scheduler_evidence"] == (
        "captured_raw_bjobs_output_hash_plus_live_same_job_recheck"
    )
    for key in (
        "policy",
        "controller",
        "internal_document_schema",
        "internal_document_validator",
        "force_prediction_runner",
        "training_data_builder",
        "checkpoint_validator",
        "gpu_finetune_job",
        "ts_domain_gate",
    ):
        assert (ROOT / active_learning[key]).is_file(), key
    assert active_learning["sequence"] == [
        "predicted_ba_sella_candidate",
        "work_structure_and_provenance_review",
        "sunboquan_codex_static_force_label",
        "work_completion_and_electronic_convergence_gate",
        "mz73_exact_structure_force_prediction",
        "work_force_error_assessment",
        "adsorption_replay_plus_held_out_regression",
        "mz73_force_only_finetuning_when_required",
        "checkpoint_load_and_regression_validation",
        "mz73_ba_sella_rerun_with_new_checkpoint",
        "independent_vasp_labeled_ts_domain_validation",
        "repeat_or_handoff_to_vasp_refinement",
    ]
def test_execution_backend_contract_keeps_source_specific_connectivity_policy() -> None:
    contract = yaml.safe_load(
        (ROOT / "configs" / "execution_backends.yaml").read_text(encoding="utf-8")
    )
    rules = contract["scientific_rules"]
    assert rules["grade_a_requires_validated_vibrational_mode"] is True
    assert rules["dimer_grade_a_requires_bidirectional_connectivity"] is False
    assert rules["dimer_bidirectional_connectivity_role"] == (
        "optional_diagnostic_not_ts_acceptance_gate"
    )
    assert rules["neb_ci_neb_bidirectional_connectivity_policy"] == (
        "required_unchanged"
    )
    assert rules["active_learning_force_label_energy_may_enter_final_energy_tables"] is False
    assert rules["active_learning_convergence_implies_valid_transition_state"] is False
    assert rules["final_ts_result_requires_completed_converged_vasp_refinement"] is True


def test_root_contains_no_executable_or_download_clutter() -> None:
    forbidden_suffixes = {".py", ".js", ".html", ".xyz"}
    offenders = [path.name for path in ROOT.iterdir() if path.is_file() and path.suffix.lower() in forbidden_suffixes]
    assert offenders == []
    allowed_directories = {
        ".git",
        ".github",
        ".pytest_cache",
        ".ruff_cache",
        "archive",
        "artifacts",
        "calculations",
        "configs",
        "data",
        "docs",
        "logs",
        "modules",
        "outputs",
        "reports",
        "scripts",
        "sbq_catalyst_agent_workflow.egg-info",  # Generated by this project's editable install.
        "skills",
        "tasks",
        "tests",
    }
    unexpected = sorted(path.name for path in ROOT.iterdir() if path.is_dir() and path.name not in allowed_directories)
    assert unexpected == []
    _assert_exact_artifact_layout(ROOT / "artifacts")


@pytest.mark.parametrize(
    ("directory", "accepted"),
    [
        ("sbq_catalyst_agent_workflow.egg-info", True),
        ("unrelated.egg-info", False),
        ("unexpected_download", False),
    ],
)
def test_root_install_metadata_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, directory: str, accepted: bool
) -> None:
    _create_exact_artifact_layout(tmp_path / "artifacts")
    (tmp_path / directory).mkdir()
    monkeypatch.setitem(globals(), "ROOT", tmp_path)
    if accepted:
        test_root_contains_no_executable_or_download_clutter()
    else:
        with pytest.raises(AssertionError):
            test_root_contains_no_executable_or_download_clutter()


def test_exact_artifact_layout_is_accepted(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    _create_exact_artifact_layout(artifacts_root)

    _assert_exact_artifact_layout(artifacts_root)


def test_review_baseline_v3_hash_bindings_match() -> None:
    binding = (
        ROOT / "artifacts" / "review_baseline_v3" / "baseline_v3_sha256.txt"
    )
    checked = 0
    for line in binding.read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        expected, relative = line.split(maxsplit=1)
        target = ROOT / relative
        assert target.is_file()
        assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
        checked += 1
    assert checked == 5


def test_undeclared_artifact_file_is_rejected(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    _create_exact_artifact_layout(artifacts_root)
    (artifacts_root / "source_baseline" / "undeclared.txt").touch()

    with pytest.raises(AssertionError):
        _assert_exact_artifact_layout(artifacts_root)


def test_undeclared_artifact_directory_is_rejected(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    _create_exact_artifact_layout(artifacts_root)
    (artifacts_root / "unapproved").mkdir()

    with pytest.raises(AssertionError):
        _assert_exact_artifact_layout(artifacts_root)


def test_calculation_copy_in_artifacts_is_rejected(tmp_path: Path) -> None:
    artifacts_root = tmp_path / "artifacts"
    _create_exact_artifact_layout(artifacts_root)
    (artifacts_root / "review_baseline_v2" / "OUTCAR").touch()

    with pytest.raises(AssertionError):
        _assert_exact_artifact_layout(artifacts_root)


def test_retired_literature_interface_does_not_return() -> None:
    forbidden = ("literature_prior_adapter", "utils_literature", "--literature-file", "use_literature_prior")
    active_files = (
        list((ROOT / "scripts" / "neb_agent").glob("*.py"))
        + list((ROOT / "scripts" / "ts_strategy_engine").glob("*.py"))
        + list((ROOT / "configs" / "neb_agent").glob("*.json"))
        + list((ROOT / "configs" / "ts_strategy_engine").glob("*.json"))
    )
    text = "\n".join(path.read_text(encoding="utf-8") for path in active_files)
    assert not any(token in text for token in forbidden)


def test_one_precalculation_retrieval_owner() -> None:
    routing = yaml.safe_load((ROOT / "configs" / "skill_routing.yaml").read_text(encoding="utf-8"))
    owner = routing["pre_calculation_external_data"]["owner"]
    assert owner == "catalysis-data-retrieval"
    assert owner not in routing["calculation_consumers"]
    assert routing["pre_calculation_external_data"]["general_literature_fallback"] is False
    adsorption_gate = routing["pre_calculation_adsorption_motif_gate"]
    assert adsorption_gate["no_whitelist_match_fallback"] == "authoritative_journals_only_after_NO_WHITELIST_MATCH"
    assert adsorption_gate["evidence_rules"] == "configs/adsmind_lite/evidence_gate.yaml"
    assert adsorption_gate["external_evidence_use"] == "structure_selection_stability_order_and_initial_geometry_only"
    assert adsorption_gate["external_energy_import"] == "forbidden"
    assert (ROOT / "skills" / owner / "SKILL.md").is_file()


def test_calculation_skills_do_not_own_external_search() -> None:
    routing = yaml.safe_load((ROOT / "configs" / "skill_routing.yaml").read_text(encoding="utf-8"))
    forbidden = ("nature-academic-search", "literature-reviewer-skill", "search several authoritative papers")
    for name in routing["calculation_consumers"]:
        skill = ROOT / "skills" / name / "SKILL.md"
        if skill.is_file():
            text = skill.read_text(encoding="utf-8")
            assert not any(token in text for token in forbidden)


def test_user_preference_ids_are_unique() -> None:
    text = (ROOT / "docs" / "09_USER_PREFERENCES.md").read_text(encoding="utf-8")
    identifiers = re.findall(r"\| `(UP-\d+)` \|", text)
    assert len(identifiers) == len(set(identifiers))


def test_module_contracts_and_status_ownership() -> None:
    module_map = (ROOT / "docs" / "06_MODULE_MAP.md").read_text(encoding="utf-8")
    statuses = re.findall(r"\| `[^`]+` \| (Planned|Active|Blocked|Completed) \|", module_map)
    assert statuses
    for module in (ROOT / "modules").iterdir():
        if not module.is_dir() or module.name == "__pycache__":
            continue
        readme = (module / "README.md").read_text(encoding="utf-8")
        assert re.search(r"(?m)^## .*Purpose", readme), module.name
        assert re.search(r"(?m)^## .*Done Criteria", readme), module.name
        assert "## Current Status" not in readme
        assert f"| `{module.name}` |" in module_map


def test_wrong_facet_generators_are_not_current_tools() -> None:
    retired = {
        "setup_fe_bulk_slab_convergence.py",
        "setup_vasp_convergence_suite.py",
        "setup_fe110_vacuum_thickness_smearing.py",
    }
    assert not any(path.is_file() for name in retired for path in (ROOT / "scripts").rglob(name))
    assert not any(path.is_file() for name in retired for path in (ROOT / "archive").rglob(name))


def test_true_and_legacy_fe_profiles_are_separated() -> None:
    profiles = yaml.safe_load((ROOT / "configs" / "incar_custodian" / "project_profiles.yaml").read_text(encoding="utf-8"))
    materials = profiles["materials"]
    assert set(materials) == {"Fe110"}
    assert "Gamma 5 5 1" in materials["Fe110"]["kpoints_note"]
    assert materials["Fe110"]["profile_source"] == "configs/true_fe110_production.yaml"
    assert "calculation_types" not in materials["Fe110"]
    assert set(materials["Fe110"]["stage_map"]) >= {"pre_NEB", "CI_NEB", "DIMER", "VFA"}

    script = ROOT / "skills" / "fe-vasp-incar-custodian" / "scripts" / "incar_custodian.py"
    spec = importlib.util.spec_from_file_location("project_incar_custodian", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    hydrated, _ = module.load_project_profiles(ROOT)
    stages = hydrated["materials"]["Fe110"]["calculation_types"]
    assert stages["pre_NEB"]["PREC"] == "Accurate"
    assert stages["DIMER"]["ICHAIN"] == 2
    assert stages["VFA"]["IBRION"] == 5


def test_true_fe110_ts_policy_locks_basis_and_registry_promotion() -> None:
    profile = yaml.safe_load((ROOT / "configs" / "true_fe110_production.yaml").read_text(encoding="utf-8"))
    vfa = profile["transition_state"]["vfa"]
    assert vfa["method"] == "finite_difference_partial_hessian"
    assert vfa["active_set_policy"]["required_atoms"] == "reaction_contract_reaction_atoms"
    assert vfa["active_set_policy"]["full_hessian_required"] is False
    assert vfa["active_set_policy"]["thermochemistry_rule"]
    policy = profile["transition_state"]["parameter_policy"]
    fixed = policy["fixed_dft_basis"]

    assert fixed["slab_layers"] == 5
    assert fixed["clean_slab_atoms"] == 45
    assert fixed["fixed_bottom_layers"] == 2
    assert fixed["functional"] == "PBE"
    assert fixed["incar_gga"] == "PE"
    assert fixed["potcar_family"] == "PAW_PBE"
    assert fixed["potcar_order"] == ["Fe", "C", "O"]
    assert fixed["encut_eV"] == 400
    assert fixed["gamma_mesh"] == [5, 5, 1]
    assert fixed["spin_polarized"] is True
    assert fixed["atom_order_and_selective_dynamics"] == "locked"
    assert fixed["compatibility_fingerprint_required"] is True

    allowed = {
        key
        for stage_keys in policy["allowed_to_vary_by_approved_stage"].values()
        for key in stage_keys
    }
    assert allowed.isdisjoint({"GGA", "ENCUT", "KPOINTS", "ISPIN", "MAGMOM", "POTCAR", "ISYM", "LDIPOL"})
    neb_controls = {"ALGO", "AMIX", "BMIX", "AMIX_MAG", "BMIX_MAG", "IMAGES", "NPAR", "core_count"}
    assert neb_controls <= set(policy["allowed_to_vary_by_approved_stage"]["ordinary_neb"])

    promotion = policy["result_promotion"]
    assert promotion["aqcat25_energy"] == "predicted_candidate_only"
    assert promotion["neb_profile_energy"] == "diagnostic_only"
    assert promotion["final_energy_profile"] == "final_energy_policy"
    assert promotion["final_energy_convention"] == "fe110_converged_toten_sigma0p20_v1"
    assert promotion["final_energy_source"] == "final_OUTCAR_TOTEN"
    assert promotion["matched_static_required"] is False
    assert promotion["registry_database"] == "data/project_registry.sqlite3"
    assert {
        "accepted_grade_a_ts",
        "validated_vibrational_mode",
        "source_method_validation_complete",
        "compatible_converged_SIGMA_0p20_IS_TS_FS_TOTEN",
        "identical_compatibility_fingerprint",
    } <= set(promotion["reportable_barrier_requires"])
    assert promotion["source_method_validation"]["dimer"] == [
        "dimer_technical_acceptance",
        "validated_vibrational_mode",
    ]
    assert promotion["source_method_validation"]["neb"] == [
        "validated_bidirectional_connectivity"
    ]
    assert promotion["source_method_validation"]["ci_neb"] == [
        "validated_bidirectional_connectivity"
    ]
