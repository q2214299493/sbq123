from __future__ import annotations

import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import pytest

from scripts.adsorption.build_fe110_adsorption import generate_sites, pair_candidates, read_poscar
from scripts.adsmind_lite.core import detect_surface_sites, generate_candidates, write_json
from scripts.adsmind_lite.generate_adsorption_candidates import new_output_directory
from scripts.adsmind_lite import generate_adsorption_candidates as generator_cli
from tests.test_adsmind_lite import CONFIG, ROOT, SLAB, write_site_plan


LAUNCHER = ROOT / "skills/surface-adsorption-builder/scripts/place_fe_co_candidates.py"


def installed_launcher(tmp_path: Path) -> Path:
    """Exercise a global-style installation with no adjacent geometry helpers."""
    target = tmp_path / "installed skill/scripts/place_fe_co_candidates.py"
    target.parent.mkdir(parents=True)
    shutil.copyfile(LAUNCHER, target)
    return target


def inputs(tmp_path: Path) -> dict:
    shutil.copyfile(SLAB, tmp_path / "POSCAR")
    sites = detect_surface_sites(SLAB, "Fe110", "metallic_fe", CONFIG / "surfaces.yaml", CONFIG / "site_rules.yaml")
    write_json(tmp_path / "sites.json", sites)
    write_site_plan(tmp_path / "plan.json", ["CO"], sites)
    return sites


def invoke(launcher: Path, tmp_path: Path, *extra: str, repository: Path = ROOT, sites: str = "sites.json"):
    return subprocess.run(
        [sys.executable, str(launcher), "POSCAR", "--repo-root", str(repository),
         "--sites", sites, "--plan", "plan.json", "--outdir", "via-skill", *extra],
        cwd=tmp_path, text=True, capture_output=True, check=False,
    )


def test_installed_launcher_matches_canonical_geometry_and_long_bridge(tmp_path):
    sites = inputs(tmp_path)
    launcher = installed_launcher(tmp_path)
    expected = generate_candidates(
        tmp_path / "POSCAR", tmp_path / "sites.json", ["CO"], CONFIG / "adsorbate_rules.yaml",
        tmp_path / "canonical", tmp_path / "plan.json",
    )
    result = invoke(launcher, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "generated=4" in result.stdout and "submitted=0" in result.stdout
    actual = [json.loads(line) for line in (tmp_path / "via-skill/candidates.jsonl").read_text().splitlines()]
    assert len(actual) == len(expected)
    by_id = {item["candidate_id"]: item for item in expected}
    for item in actual:
        reference = by_id[item["candidate_id"]]
        assert Path(item["initial_structure"]).read_bytes() == Path(reference["initial_structure"]).read_bytes()
        assert item["initial_motif"] == reference["initial_motif"]

    slab = read_poscar(SLAB)
    canonical_sites, top = generate_sites(slab)
    long_site = next(item for item in sites["sites"] if item["site_class"] == "bridge_FeFe_long")
    assert long_site["support_distance_angstrom"] == canonical_sites["long_bridge"].support_distance
    assert long_site["support_distance_angstrom"] < max(pair.distance for pair in pair_candidates(slab, top))
    assert {item["planned_site_class"] for item in actual} == {item["site_class"] for item in sites["sites"]}


def test_legacy_call_discovers_project_and_prepares_sites_with_sidecar_plan(tmp_path):
    inputs(tmp_path)
    original_plan = (tmp_path / "plan.json").read_bytes()
    launcher = installed_launcher(tmp_path)
    result = subprocess.run(
        [sys.executable, str(launcher), str(tmp_path / "POSCAR"), "--outdir", str(tmp_path / "via-skill")],
        cwd=ROOT, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert f"repository={ROOT}" in result.stdout
    assert "generated=4" in result.stdout
    assert (tmp_path / "via-skill/_inputs/sites.json").is_file()
    assert not (tmp_path / "via-skill/_inputs/plan.json").exists()
    assert (tmp_path / "plan.json").read_bytes() == original_plan
    actual = [json.loads(line) for line in (tmp_path / "via-skill/candidates.jsonl").read_text().splitlines()]
    expected = generate_candidates(
        tmp_path / "POSCAR", tmp_path / "sites.json", ["CO"], CONFIG / "adsorbate_rules.yaml",
        tmp_path / "canonical", tmp_path / "plan.json",
    )
    assert [Path(item["initial_structure"]).read_bytes() for item in actual] == [
        Path(item["initial_structure"]).read_bytes() for item in expected
    ]


def test_legacy_call_without_plan_prepares_draft_and_preserves_evidence_gate(tmp_path):
    launcher = installed_launcher(tmp_path)
    shutil.copyfile(SLAB, tmp_path / "POSCAR")
    result = subprocess.run(
        [sys.executable, str(launcher), "POSCAR", "--repo-root", str(ROOT), "--outdir", "via-skill"],
        cwd=tmp_path, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    draft = json.loads((tmp_path / "via-skill/_inputs/plan.json").read_text())
    assert draft["species_plans"][0]["decision"] == "NEEDS_WHITELIST"
    assert "NEEDS_WHITELIST" in result.stdout + result.stderr
    assert (tmp_path / "via-skill/_inputs/sites.json").is_file()
    assert not (tmp_path / "via-skill/candidates.jsonl").exists()
    assert not list((tmp_path / "via-skill").rglob("POSCAR"))


def test_legacy_call_without_project_context_explains_required_context(tmp_path):
    launcher = installed_launcher(tmp_path)
    shutil.copyfile(SLAB, tmp_path / "POSCAR")
    result = subprocess.run(
        [sys.executable, str(launcher), "POSCAR", "--outdir", "via-skill"],
        cwd=tmp_path, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    assert "Cannot identify one canonical repository (none); use --repo-root" in result.stderr
    assert not (tmp_path / "via-skill/candidates.jsonl").exists()
    assert not list((tmp_path / "via-skill").rglob("POSCAR"))


def test_installed_launcher_preserves_repository_coverage_gate(tmp_path):
    inputs(tmp_path)
    launcher = installed_launcher(tmp_path)
    path = tmp_path / "plan.json"
    plan = json.loads(path.read_text())
    item = plan["species_plans"][0]
    top = item["candidates"][0]
    item["candidates"] = [{**top, "motif_id": "rotation_" + str(angle), "orientation_degrees": angle}
                          for angle in (0, 90, 180)]
    write_json(path, plan)
    result = invoke(launcher, tmp_path)
    assert result.returncode == 1
    assert "initial_motif_coverage 1/3" in result.stderr
    assert not (tmp_path / "via-skill/candidates.jsonl").exists()
    assert not list((tmp_path / "via-skill").rglob("POSCAR"))


def test_installed_launcher_rejects_missing_repository(tmp_path):
    inputs(tmp_path)
    result = invoke(installed_launcher(tmp_path), tmp_path, repository=tmp_path)
    assert result.returncode == 2
    assert "Missing canonical repository file" in result.stderr
    assert not (tmp_path / "via-skill").exists()


def test_installed_launcher_rejects_legacy_site_name_list(tmp_path):
    inputs(tmp_path)
    result = invoke(installed_launcher(tmp_path), tmp_path, sites="top,long_bridge")
    assert result.returncode == 2
    assert "Missing sites JSON file" in result.stderr
    assert not (tmp_path / "via-skill").exists()


def test_installed_launcher_rejects_standalone_geometry_overrides(tmp_path):
    inputs(tmp_path)
    result = invoke(installed_launcher(tmp_path), tmp_path, "--c-height", "1.85", "--co-length", "1.15", "--top-tol", "0.03")
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr
    assert not (tmp_path / "via-skill").exists()


def test_repository_discovery_uses_slab_ancestors_and_rejects_ambiguity(tmp_path, monkeypatch):
    namespace = runpy.run_path(str(LAUNCHER))
    find_repository = namespace["find_repository"]

    def project(path):
        for relative in namespace["REPOSITORY_FILES"]:
            marker = path / relative
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("test marker")
        return path

    caller = tmp_path / "caller"
    caller.mkdir()
    monkeypatch.chdir(caller)
    slab_project = project(tmp_path / "slab-project")
    surface = slab_project / "inputs/slab/POSCAR"
    assert find_repository(surface) == slab_project
    project(caller)
    with pytest.raises(ValueError, match="Cannot identify one canonical repository"):
        find_repository(surface)
    assert find_repository(surface, caller) == caller


def test_auto_output_is_new_and_existing_explicit_output_is_rejected(tmp_path):
    base = tmp_path / "data/candidates/co_candidates"
    assert new_output_directory(base, numbered=True) == base
    sentinel = base / "existing-result.txt"
    sentinel.write_bytes(b"keep original result")
    assert new_output_directory(base, numbered=True) == base.with_name("co_candidates_002")
    with pytest.raises(ValueError, match="Output already exists"):
        new_output_directory(base, numbered=False)
    assert sentinel.read_bytes() == b"keep original result"


def test_generator_prepares_all_missing_inputs_in_project_runtime(tmp_path, monkeypatch):
    inputs(tmp_path)
    repository = tmp_path / "project"
    for relative in ("pyproject.toml", "configs/state_handoff.yaml", "configs/skill_routing.yaml",
                     "configs/adsmind_lite/surfaces.yaml", "configs/adsmind_lite/site_rules.yaml"):
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)
    monkeypatch.setattr(generator_cli, "ROOT", repository)
    monkeypatch.setattr(sys, "argv", ["generate_adsorption_candidates", "--surface", str(tmp_path / "POSCAR"),
                                     "--adsorbates", "CO", "--prepare-missing"])
    generator_cli.main()
    output = repository / "modules/adsmind_lite/data/candidates/co_candidates"
    assert (output / "_inputs/sites.json").is_file()
    assert not (output / "_inputs/plan.json").exists()
    assert len((output / "candidates.jsonl").read_text().splitlines()) == 4


def test_sidecar_ambiguity_requires_selection_before_writing(tmp_path):
    inputs(tmp_path)
    shutil.copyfile(tmp_path / "plan.json", tmp_path / "prescreen_plan.json")
    result = subprocess.run(
        [sys.executable, str(installed_launcher(tmp_path)), "POSCAR", "--repo-root", str(ROOT), "--outdir", "via-skill"],
        cwd=tmp_path, text=True, capture_output=True, check=False,
    )
    assert result.returncode == 1
    assert "Multiple sidecar plans" in result.stderr
    assert not (tmp_path / "via-skill").exists()
