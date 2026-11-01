"""Prepare twelve review-only seeds; never load an ML model or execute VASP."""
from __future__ import annotations

from dataclasses import replace
import gzip
import itertools
import json
import shutil
from pathlib import Path
import zipfile

import numpy as np
import yaml

from scripts.artifact_io import sha256_file, write_json_exclusive
from scripts.adsorption.build_fe110_adsorption import (
    Poscar, expanded_symbols, generate_sites, read_poscar, write_poscar,
)
from scripts.adsorption.build_fe110_care_batch import (
    draw_pose, molecular_signature, pose_measurements,
)
from scripts.adsorption.build_fe110_care_isomers import (
    care_source_pose, connectivity, equivalent_pose_rmsd, review,
    rigid_reanchor_pose, surface_pose_symmetries, transfer_pose,
)

ROOT = Path(__file__).resolve().parents[2]
TASK = ROOT / "calculations/fe110_c2_adsorption_16_19_20261101"
OUT = TASK / "review_ready_v2"
SLAB = ROOT / "calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
NETWORK = Path("C:/Users/86177/Desktop/app/CARE_Fe110_FT_C1_C6/evaluated_networks/ft_C2O1_Fe110_eval.pkl.json.gz")
REUSE = ROOT / "calculations/fe110_c2h4o_adsorption_20261029/review_ready"
EXPECTED_SLAB = "3337ad4e89a2719551035fadbd5082a60c12cafcadc14748d8b48a198379109d"
EXPECTED_NETWORK = "c4de04dd8c4ba99ea16977ffa0fe44752baa13d85f768535a7e0bd0d6a8f1632"
SIGNATURES = {
    "16": [["C", 0, ["C", "O"]], ["C", 3, ["C"]], ["O", 1, ["C"]]],
    "17": [["C", 2, ["C"]], ["C", 2, ["C", "O"]], ["O", 0, ["C"]]],
    "18": [["C", 1, ["O"]], ["C", 3, ["O"]], ["O", 0, ["C", "C"]]],
    "19": [["C", 3, ["C"]], ["C", 3, ["C"]]],
}


def canonical_order(pose: Poscar) -> Poscar:
    symbols = expanded_symbols(pose)
    species = [symbol for symbol in ("Fe", "C", "O", "H") if symbol in symbols]
    order = [i for symbol in species for i, element in enumerate(symbols) if element == symbol]
    return replace(pose, symbols=species, counts=[symbols.count(s) for s in species],
                   frac=pose.frac[order].copy(), flags=[pose.flags[i] for i in order])


def seed_rmsd(first: Poscar, second: Poscar, operations: list, number: str) -> float:
    value = equivalent_pose_rmsd(first, second, operations)
    if number == "19":
        # Ethane's two carbon atoms are chemically interchangeable. The owner
        # already handles all H permutations and face-preserving slab symmetry.
        permuted = second.frac.copy()
        permuted[[45, 46]] = permuted[[46, 45]]
        value = min(value, equivalent_pose_rmsd(first, replace(second, frac=permuted), operations))
    return value


def validate_seed(pose: Poscar, slab: Poscar, number: str) -> dict:
    expected = [45, 2, 6] if number == "19" else [45, 2, 1, 4]
    if pose.counts != expected or molecular_signature(pose) != SIGNATURES[number]:
        raise ValueError("wrong composition or isomer connectivity")
    if not np.allclose(pose.cell, slab.cell, rtol=0, atol=1e-12):
        raise ValueError("changed slab cell")
    if not np.allclose(pose.frac[:45], slab.frac, rtol=0, atol=1e-12):
        raise ValueError("changed clean-slab coordinates")
    if pose.flags[:45] != slab.flags or pose.flags[45:] != [("T", "T", "T")] * (sum(expected) - 45):
        raise ValueError("changed fixed-layer or adsorbate mask")
    result = review(pose, pose, list(range(45, sum(expected))))
    if result["verdict"] != "pass":
        raise ValueError("unsafe starting geometry: " + str(result["checks"]))
    return result


def constructed_seed(parent, slab, sites, operations, kept, number, tolerance):
    proposals = []
    # A third carbene approach may use the locally observed top-site anchor.
    # This is a single fallback candidate, not a mandatory four-site output set.
    candidate_sites = ("short_bridge", "hollow", "long_bridge", "top") if number == "18" else ("short_bridge", "hollow", "long_bridge")
    for site_name, tilt, azimuth, distance in itertools.product(
        candidate_sites, (0., 15., 30.),
        (0., 45., 90., 135., 180., 225., 270., 315.), (2.25, 2.40, 2.55, 2.70),
    ):
        pose = rigid_reanchor_pose(parent, slab, sites[site_name], anchor=45, axis_to=46 if number == "16" else 47,
                                   azimuth_deg=azimuth, tilt_deg=tilt, binding_distance_A=distance)
        xyz = pose.frac @ pose.cell
        if min(xyz[45:, 2]) - max(xyz[:45, 2]) < 1.35:
            continue
        # A geometric triage score, deliberately not an energy/stability score.
        proposals.append((abs(distance - 2.25), site_name, tilt, azimuth, distance, pose))
    warned = None
    for _, site_name, tilt, azimuth, distance, pose in sorted(proposals, key=lambda x: x[:5]):
        try:
            audit = validate_seed(pose, slab, number)
        except ValueError:
            continue
        rmsd = min(seed_rmsd(pose, old, operations, number) for old, _ in kept)
        if rmsd <= max(tolerance, .50):
            continue
        result = (pose, {"origin": "EXPLORATORY_RIGID_REANCHOR", "source_config": "1",
                         "recipe": {"site": site_name, "tilt_deg": tilt, "azimuth_deg": azimuth,
                                    "binding_distance_A": distance, "anchor_zero_based": 45},
                         "selection_basis": "Safe geometry and seed inequivalence only; not an energy ranking."})
        if not audit["warnings"]:
            return result
        if warned is None or len(audit["warnings"]) < warned[0]:
            warned = (len(audit["warnings"]), result)
    if warned is not None:
        return warned[1]
    raise ValueError(f"No safe third inequivalent seed for {number}; do not pad the batch")


def prepare_species(species, network, slab, sites, operations, tolerance):
    number = species["number"]
    if number == "17":
        old = json.loads((REUSE / "candidate_review.json").read_text(encoding="utf-8"))
        if old["slab_sha256"] != EXPECTED_SLAB:
            raise ValueError("reused row17 slab branch mismatch")
        kept = []
        for item in old["candidates"]:
            path = REUSE / item["name"] / "POSCAR"
            if sha256_file(path) != item["POSCAR_sha256"]:
                raise ValueError("reused row17 source changed")
            kept.append((read_poscar(path), {"origin": "BYTE_EXACT_REUSE_OF_REVIEWED_EXPLORATORY_SEED",
                                           "source_path": str(path), "source_config": None}))
        return kept
    source = next(v for k, v in network["species_registry"].items()
                  if k.split("-", 1)[0] == species["care_prefix"] and v["phase"] == "ads")
    parents = {}
    for config, raw in sorted(source["ads_configs"].items()):
        original, _ = care_source_pose(raw)
        transferred, _ = transfer_pose(original, slab)
        parent = canonical_order(transferred)
        if molecular_signature(parent) != SIGNATURES[number]:
            raise ValueError("CARE molecular identity mismatch")
        parents[config] = parent
    if number == "19":
        kept = []
        for config, site, tilt, azimuth, distance in [
            ("0", "top", 0., 0., 3.10),
            ("1", "long_bridge", 30., 90., 3.20),
            ("2", "top", 70., 45., 3.10),
        ]:
            pose = rigid_reanchor_pose(parents[config], slab, sites[site], anchor=45, axis_to=46,
                                       azimuth_deg=azimuth, tilt_deg=tilt, binding_distance_A=distance)
            kept.append((pose, {"origin": "INTACT_ETHANE_MOLECULAR_APPROACH", "source_config": config,
                               "recipe": {"site": site, "tilt_deg": tilt, "azimuth_deg": azimuth,
                                          "binding_distance_A": distance},
                               "warning": "Closed-shell molecule; weak adsorption, desorption or dehydrogenation must be reviewed after optimization."}))
        return kept
    kept = []
    for config in ("0", "2", "1"):
        pose = parents[config]
        if number == "18":
            frac = pose.frac.copy()
            frac[45:] += np.array([0., 0., .20]) @ np.linalg.inv(slab.cell)
            pose = replace(pose, frac=frac)
        audit = validate_seed(pose, slab, number)
        if audit["warnings"]:
            continue
        if kept and min(seed_rmsd(pose, old, operations, number) for old, _ in kept) <= tolerance:
            continue
        kept.append((pose, {"origin": "LOCAL_CARE_MOLECULAR_GEOMETRY_TRANSFER", "source_config": config,
                           "height_adjustment_A": .20 if number == "18" else 0.,
                           "source_energy_used": False}))
        if number == "16" and len(kept) == 2:
            # The third raw CARE pose was only0.205A from the first at the0.20A
            # duplicate boundary. Select a more diverse third placement instead.
            break
    while len(kept) < 3:
        kept.append(constructed_seed(parents["1"], slab, sites, operations, kept, number, tolerance))
    return kept[:3]


def main():
    if OUT.exists():
        raise FileExistsError("Preserve prior outputs; use a new reviewed version")
    if sha256_file(SLAB) != EXPECTED_SLAB or sha256_file(NETWORK) != EXPECTED_NETWORK:
        raise ValueError("accepted source binding changed")
    request = json.loads((TASK / "request.json").read_text(encoding="utf-8"))
    slab = read_poscar(SLAB)
    with gzip.open(NETWORK, "rt", encoding="utf-8") as stream:
        network = json.load(stream)
    sites, _ = generate_sites(slab)
    operations = surface_pose_symmetries(slab)
    rules_path = ROOT / "configs/adsmind_lite/analysis_rules.yaml"
    tolerance = yaml.safe_load(rules_path.read_text())["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"]
    all_poses, records, pairwise = {}, [], []
    for species in request["species"]:
        number = species["number"]
        kept = prepare_species(species, network, slab, sites, operations, tolerance)
        if len(kept) != 3:
            raise ValueError("requested three seeds not obtained")
        for letter, (pose, metadata) in zip("ABC", kept, strict=True):
            name = number + "_" + letter
            audit = validate_seed(pose, slab, number)
            all_poses[name] = pose
            records.append({"name": name, "species_number": number, "formula": species["formula"],
                            "connectivity": species["connectivity"], "care_prefix": species["care_prefix"],
                            **metadata, "geometry_review": audit, **pose_measurements(pose)})
        for i, j in itertools.combinations(range(3), 2):
            value = seed_rmsd(kept[i][0], kept[j][0], operations, number)
            if value <= tolerance:
                raise ValueError("near-duplicate seeds do not satisfy the requested count")
            pairwise.append({"species_number": number, "pair": ["ABC"[i], "ABC"[j]], "RMSD_A": value})
    OUT.mkdir()
    for record in records:
        path = OUT / record["name"] / "POSCAR"
        if record["origin"].startswith("BYTE_EXACT_REUSE"):
            path.parent.mkdir()
            shutil.copyfile(record["source_path"], path)
        else:
            write_poscar(path, all_poses[record["name"]])
        record.update({"structure": str(path), "structure_sha256": sha256_file(path),
                       "energy_eV": None, "relaxed": False, "scientific_acceptance": False})
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    for species in request["species"]:
        number = species["number"]
        fig, axes = plt.subplots(2, 3, figsize=(15, 8), constrained_layout=True)
        for column, letter in enumerate("ABC"):
            draw_pose(axes[:, column], all_poses[number + "_" + letter], slab, number + "_" + letter)
            for ax in axes[:, column]:
                for label in list(ax.texts):
                    if label.get_text().startswith("H"):
                        label.remove()
        fig.suptitle(number + " " + species["connectivity"] + " | Fe(110), Fe45, fixed Fe0-17\nExploratory seeds only: NOT optimized or energy-ranked. Fe gray / C black / O red / H blue.")
        fig.savefig(OUT / (number + "_structures.png"), dpi=145)
        plt.close(fig)
    manifest = {"status": "PREPARED_FOR_STRUCTURE_REVIEW_ONLY", "candidate_count": len(records),
                "scientific_acceptance": False, "gpu_ready": False, "submitted": False,
                "source_slab": str(SLAB), "source_slab_sha256": EXPECTED_SLAB,
                "source_network": str(NETWORK), "source_network_sha256": EXPECTED_NETWORK,
                "request_sha256": sha256_file(TASK / "request.json"),
                "image_query_sha256": sha256_file(TASK / "image_query.json"),
                "literature_screening_sha256": sha256_file(TASK / "literature_screening.json"),
                "stable_top_three_claim": False, "source_energies_imported": False,
                "execution": {"GPU": 0, "VASP": 0}, "candidates": records,
                "seed_only_deduplication": {"RMSD_threshold_A": tolerance, "slab_operations": len(operations),
                                            "height_shift_removed": True, "ethane_C_exchange_checked": True,
                                            "constructed_seed_diversity_preference_A": .50,
                                            "pairwise": pairwise},
                "ML_domain_caveat": "Seven/eight adsorbate atoms exceed the documented 2-6 near-relaxed AQCat gate. New calibration or an explicit uncalibrated-candidate review is required before model ranking is trusted.",
                "builder_sha256": sha256_file(Path(__file__))}
    write_json_exclusive(OUT / "candidate_review.json", manifest)
    lines = ["# Fe(110) 16–19: twelve exploratory candidates", "",
             "未优化、未排序、未提交；不是文献已证实的三个最低能稳定态。17_A/B/C逐字节复用先前已审几何候选。", "",
             "Fe45五层、原晶胞及Fe坐标不变；零基Fe0–17固定，其余原子可动。C2H4O采用Fe C O H顺序，C2H6采用Fe C H。", "",
             "|候选|连接方式|C45最近Fe/Å|C46最近Fe/Å|O47最近Fe/Å|软警告|",
             "|---|---|---|---|---|---|"]
    for item in records:
        nearest = item["nearest_Fe"]
        values = ["Fe" + str(nearest[i]["neighbors"][0]["Fe_index_0based"]) + ":" + f"{nearest[i]['neighbors'][0]['distance_A']:.3f}" for i in range(3 if item["species_number"] != "19" else 2)]
        if len(values) == 2:
            values.append("—")
        lines.append("|" + "|".join([item["name"], item["connectivity"], *values,
                                     "; ".join(item["geometry_review"]["warnings"]) or "无"]) + "|")
    lines += ["", "种内三对候选均通过去除整体高度差、Fe表面真实对称操作和H置换的初始几何去重；乙烷另检查C互换。此项不证明优化后仍为不同极小值。", "",
              "16为CH3-[C]-OH，18为[CH]-O-CH3；不得替换成乙醇/二甲醚。19为完整乙烷的平躺/倾斜/近直立接近构型，不预设C-Fe强键；后续须审核弱吸附、脱附和脱氢。", "",
              "全部为7–8个吸附物原子的新化学范围，不能宣称已在旧AQCat近极小值域校准。GPU与DFT均须后续独立审核授权；不修改原15个运行/已结束作业。", ""]
    (OUT / "structure_review.md").write_text("\n".join(lines), encoding="utf-8")
    archive = TASK / "Fe110_16_19_12_candidates_v2.zip"
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(OUT.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(OUT).as_posix())
    print(json.dumps({"status": manifest["status"], "candidate_count": len(records),
                      "pairwise_RMSD_A": pairwise, "output": str(OUT), "archive": str(archive)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
