import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from ase.io import write

from archive.fe110_adsorption_validation_20261018.runtime import verify_labels
from scripts.adsorption.reico_sampling import UNLABELED_ROLE, run_sampling, validate_sampling_scope
from scripts.artifact_io import sha256_file
from tests.test_reico_sampling import GUARDS, LIMITS, atoms_fixture, scope


def test_unlabeled_role_requires_its_own_exact_exception():
    request, auth, sha, exception = scope()
    request["sample_role"] = UNLABELED_ROLE
    with pytest.raises(ValueError, match="role changed"):
        validate_sampling_scope(request, auth, sha, exception)
    exception["sample_role"] = UNLABELED_ROLE
    request["max_return_bytes"] = exception["max_return_bytes"] = 96_000_000
    validate_sampling_scope(request, auth, sha, exception)
    request["max_return_bytes"] += 1
    with pytest.raises(ValueError, match="size cap"):
        validate_sampling_scope(request, auth, sha, exception)


def dump(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return sha256_file(path)


@pytest.fixture
def unlabeled(tmp_path):
    atoms = atoms_fixture()
    write(tmp_path / "source.vasp", atoms, format="vasp", direct=True)
    write(tmp_path / "slab.vasp", atoms[:45], format="vasp", direct=True)
    config_sha = dump(tmp_path / "config.json", {"pair_minimum_A": GUARDS})
    family = {"family_id": "family_one", "partition": "final_test", "composition": "CH",
              "status": "CPU_GEOMETRY_CANDIDATE", "poscar_sha256": sha256_file(tmp_path / "source.vasp")}
    record_sha = dump(tmp_path / "family.json", family)
    row = {"sample_id": "family_one", "source_name": "family_one", "partition": "final_test",
           "composition": "CH", "structure_path": "source.vasp", "structure_sha256": family["poscar_sha256"],
           "family_record_path": "family.json", "family_record_sha256": record_sha,
           "symbols": atoms.get_chemical_symbols(), "fixed_atom_indices_0based": list(range(18))}
    summary = {"binding": {"config_sha256": config_sha, "slab_sha256": sha256_file(tmp_path / "slab.vasp")},
               "families": [family]}
    summary_sha = dump(tmp_path / "summary.json", summary)
    source = {"document_kind": "frozen_reico_unlabeled_sampling_sources", "samples": [row],
              "generation_summary_path": "summary.json", "generation_summary_sha256": summary_sha,
              "slab_path": "slab.vasp"}
    source_sha = dump(tmp_path / "sources.json", source)
    request = {"document_kind": "adsorption_bounded_random_sampling", "sample_role": UNLABELED_ROLE,
               "source_manifest_path": "sources.json", "source_manifest_sha256": source_sha,
               "generation_config_path": "config.json", "generation_config_sha256": config_sha,
               "samples": copy.deepcopy([row]), "limits": LIMITS}
    return tmp_path, request


def test_actual_unlabeled_sources_do_not_require_fake_DFT_forces(unlabeled):
    root, request = unlabeled
    assert "forces_eV_per_A" not in request["samples"][0]
    verify_labels(root, request)


@pytest.mark.parametrize("change", ["partition", "structure", "record", "summary", "config", "slab"])
def test_changed_generation_evidence_rejected(unlabeled, change):
    root, request = unlabeled
    if change == "partition":
        request["samples"][0]["partition"] = "train"
    else:
        names = {"structure": "source.vasp", "record": "family.json", "summary": "summary.json",
                 "config": "config.json", "slab": "slab.vasp"}
        with (root / names[change]).open("a") as handle:
            handle.write("changed")
    with pytest.raises(ValueError):
        verify_labels(root, request)


def test_sampling_keeps_frozen_final_test_partition(unlabeled, monkeypatch):
    root, request = unlabeled
    import scripts.adsorption.reico_sampling as module
    monkeypatch.setattr(module, "sample_case", lambda *args: {"frames": [], "optimizer_steps": 0, "status": "UNIT_FIXTURE"})
    request["models"] = {"candidate": {"sha256": "a" * 64}}
    result = run_sampling(root, request, object(), 100)
    assert result["cases"][0]["partition"] == "final_test"
    assert result["cases"][0]["source_structure_sha256"] == request["samples"][0]["structure_sha256"]


def test_legacy_standalone_runtime_does_not_require_optional_sampler(tmp_path):
    root = Path(__file__).resolve().parents[1] / "archive/fe110_adsorption_validation_20261018"
    for name in ("runtime.py", "validation_helpers.py"):
        shutil.copy2(root / name, tmp_path / name)
    result = subprocess.run([sys.executable, str(tmp_path / "runtime.py"), "--help"],
                            cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
