"""Reorient the intact CH-C-O local template; never stitch separated ML fragments."""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import yaml

from archive.fe110_five_c2_adsorption_20261006.build_supplement import (
    make_variant, equivalent_rmsd, surface_symmetries, draw_candidate,
)
from scripts.adsorption.build_fe110_adsorption import read_poscar, generate_sites, write_poscar
from scripts.adsorption.build_fe110_care_isomers import review
from scripts.artifact_io import sha256_file, write_json

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
DEST = BASE / "supplement_repair_v1"


def main():
    if DEST.exists():
        raise FileExistsError("Preserve previous geometry proposals")
    original_path = BASE / "candidate_review.json"
    original = json.loads(original_path.read_text())
    metadata = next(c for c in original["candidates"] if c["species_id"] == "03" and c["config_id"] == "0")
    source_path = ROOT / metadata["structure"]
    assert sha256_file(source_path) == metadata["structure_sha256"]
    slab_path = ROOT / original["slab"]
    assert sha256_file(slab_path) == original["slab_sha256"]
    source, slab = read_poscar(source_path), read_poscar(slab_path)
    sites, _ = generate_sites(slab)
    spec = {"name": "03_extra2_repair_v1", "species_id": "03", "anchor_global_0based": 46,
            "site": "short_bridge", "azimuth_deg": 0.0, "tilt_deg": 0.0,
            "axis_from": 46, "axis_to": 45, "binding_distance_A": 2.20,
            "hypothesis": "Central C46 anchors at short bridge; intact CH-C-O chain parallel to long Fe rows, without pulling its two carbons toward opposed transverse sites."}
    candidate = make_variant(source, slab, sites, spec, spec["binding_distance_A"])
    initial_review = review(source, candidate, [45, 46, 47, 48])
    assert initial_review["verdict"] == "pass" and not initial_review["warnings"]
    assert initial_review["maximum_bond_length_change_angstrom"] < 1e-10
    symmetry = surface_symmetries(slab)
    comparisons = [("original_cfg"+c["config_id"], ROOT / c["structure"]) for c in original["candidates"] if c["species_id"] == "03"]
    comparisons += [("03_extra1_ML", BASE / "gpu_supplement_v1/03_extra1/output/job_2142/POSCAR"),
                    ("03_extra1_seed", BASE / "supplement_v1/03_extra1/POSCAR"),
                    ("03_extra2_failed_seed", BASE / "supplement_v1/03_extra2/POSCAR")]
    rmsds = {name: equivalent_rmsd(candidate, read_poscar(path), symmetry) for name, path in comparisons}
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text())
    assert min(rmsds.values()) > rules["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"]
    DEST.mkdir()
    target = DEST / spec["name"] / "POSCAR"
    write_poscar(target, candidate)
    reread = read_poscar(target)
    assert np.allclose(reread.frac[:45], slab.frac, atol=1e-12)
    assert reread.flags == candidate.flags
    failed_review_path = BASE / "gpu_supplement_review_v1/review.json"
    failed_record = next(r for r in json.loads(failed_review_path.read_text())["records"] if r["name"] == "03_extra2")
    assert failed_record["geometry"]["chemistry"]["dissociated"]
    plan = {"user_request": "对剩下四个进行审核去重 剩下一个做修改",
            "identity": metadata["care_code"] + " " + metadata["connectivity"], "recipe": spec,
            "source_kind": "same_intact_user_owned_local_CARE_template_rigid_reorientation",
            "source_path": source_path.relative_to(ROOT).as_posix(), "source_sha256": sha256_file(source_path),
            "slab_sha256": sha256_file(slab_path), "original_review_sha256": sha256_file(original_path),
            "failed_review_sha256": sha256_file(failed_review_path),
            "failed_output_sha256": failed_record["source_structure_sha256"],
            "observed_failure": "CC1.5349A ->2.9355A; CH and CO fragments retain bonds. This is ML dissociation evidence, not proof that the actual DFT intact state is unstable.",
            "change": "Anchor CH-C45 long bridge -> central C46 short bridge; chain azimuth90 ->0degrees, tilt10 ->0degrees. Original internal geometry and all45clean-slab Fe positions preserved.",
            "not_changed": ["atom order", "exact graph and internal bond lengths", "cell", "fixedFe0-17", "model checkpoint", "DFT protocol"],
            "constraints": "Only original bottom18Fe fixed; no bond, height or adsorption-site restraints added.",
            "geometry": initial_review, "symmetry_RMSD_A_height_removed_initial_seed_only": rmsds,
            "structure_path": target.relative_to(ROOT).as_posix(), "structure_sha256": sha256_file(target),
            "status": "GEOMETRY_PASS_UNRELAXED_REVIEW_ONLY", "gpu_submitted": False, "vasp_submitted": False,
            "scientific_acceptance": False, "risk": "Reorientation may still dissociate or merge during relaxation; no force/model-error conclusion without same-structure VASP evidence."}
    write_json(DEST / "repair_review.json", plan)
    fig, axes = plt.subplots(3, 2, figsize=(10, 10), constrained_layout=True)
    seeds = [BASE / "supplement_v1/03_extra2/POSCAR", BASE / "gpu_supplement_v1/03_extra2/output/job_2142/POSCAR", target]
    for row, path in enumerate(seeds):
        structure = read_poscar(path)
        current_spec = {"name": ["original intact seed", "ML returned CH + CO fragments", "new intact central-C seed"][row],
                        "azimuth_deg": 90.0 if row < 2 else 0.0}
        current_geometry = {"connectivity_edges_local_0based": [(0, 3), (1, 2)]} if row == 1 else initial_review
        draw_candidate(axes[row], structure, current_spec, current_geometry, slab)
    fig.suptitle("CH-C-O adsorption repair: original / failed ML / new proposal\nZero-based atom indices; new seed is NOT relaxed", fontsize=11)
    fig.savefig(DEST / "repair_comparison.png", dpi=140)
    plt.close(fig)
    print(json.dumps({"status": plan["status"], "recipe": spec, "geometry": initial_review, "minimum_symmetry_RMSD_A": min(rmsds.values())}))


if __name__ == "__main__":
    main()
