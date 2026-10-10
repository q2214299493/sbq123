"""Local adsorption adaptation review; never submits or trains a model."""

import argparse
import base64
import json
import subprocess
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from scripts.artifact_io import sha256_file, write_json_exclusive

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "calculations/fe110_five_c2_adsorption_20261006"
SOURCE = BASE / "adsorption_acceleration_rebuild_v2"
DEST = BASE / "adsorption_finetune_review_v1"
REPLAY = ROOT / "outputs/aqcat25_fe45_calibration_v1/labels.json"


def preserve_bytes(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError("partial preparation source changed")
    else:
        with path.open("xb") as handle:
            handle.write(data)

REMOTE_INPUT_READER = r'''
import base64,hashlib,json,re
from pathlib import Path
for item in RECORDS:
 root=Path(item['source_directory'].replace('~',str(Path.home()),1))
 result={'sample_id':item['sample_id'],'source_directory':str(root),'files':{}}
 for name in ('INCAR','KPOINTS','POSCAR','CONTCAR'):
  path=root/name
  if not path.is_file():
   result['files'][name]={'missing':True};continue
  data=path.read_bytes()
  if len(data)>65536:raise ValueError('unexpectedly large '+str(path))
  result['files'][name]={'sha256':hashlib.sha256(data).hexdigest(),'base64':base64.b64encode(data).decode()}
 path=root/'POTCAR'
 if path.is_file():
  data=path.read_bytes();blocks=[]
  for block in data.split(b'End of Dataset')[:-1]:
   # Keep exact per-species bytes, including their leading newline.
   blocks.append({'titel':re.search(rb'TITEL\s*=\s*([^\r\n]+)',block).group(1).decode().strip(),
    'sha256':hashlib.sha256(block+b'End of Dataset').hexdigest()})
  result['POTCAR']={'sha256':hashlib.sha256(data).hexdigest(),'blocks':blocks}
 else:result['POTCAR']={'missing':True}
 print(json.dumps(result),flush=True)
'''

REMOTE_LABEL_READER = r'''
import base64,hashlib,json,re,sys
from pathlib import Path
for item in RECORDS:
 print('binding '+item['sample_id'],file=sys.stderr,flush=True)
 root=Path(item['source_directory']);out=root/'OUTCAR';before=out.stat()
 with out.open('rb') as f:
  f.seek(max(0,before.st_size-4000000));tail=f.read(4000000)
 starts=list(re.finditer(rb'TOTAL-FORCE \(eV/Angst\)',tail))
 if not starts:raise ValueError('missing final force block')
 start=starts[-1].start();rows=[];tokens=[];used=0
 for line in tail[start:].splitlines(keepends=True):
  used+=len(line);parts=line.split()
  if len(parts)==6:
   try:row=[float(v) for v in parts]
   except ValueError:continue
   rows.append(row);tokens.append([v.decode() for v in parts[:3]])
  elif rows:break
 prefix=tail[:start].decode(errors='replace')
 steps=re.findall(r'Iteration\s+(\d+)\s*\(\s*(\d+)\s*\)',prefix)
 if not steps:raise ValueError('missing electronic cycle')
 ionic,electronic=map(int,steps[-1])
 energies=re.findall(rb'free\s+energy\s+TOTEN\s*=\s*([-+0-9.Ee]+)',tail[start:])
 if not energies:raise ValueError('missing energy after final forces')
 h=hashlib.sha256()
 with out.open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 after=out.stat()
 if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('source changed')
 print(json.dumps({'sample_id':item['sample_id'],'OUTCAR_sha256':h.hexdigest(),
  'OUTCAR_bytes':before.st_size,'ionic_step':ionic,'electronic_iteration':electronic,
  'EDIFF_marker_before_force':'aborting loop because EDIFF is reached' in prefix[prefix.rfind('Iteration'):],
  'required_accuracy':b'reached required accuracy' in tail,
  'normal_footer':b'General timing and accounting informations for this job' in tail,
  'toten_eV':float(energies[-1]),'positions_A':[r[:3] for r in rows],'position_tokens':tokens,
  'forces_eV_per_A':[r[3:] for r in rows],
  'force_table_base64':base64.b64encode(tail[start:start+used]).decode(),
  'OSZICAR_base64':base64.b64encode((root/'OSZICAR').read_bytes()).decode()}),flush=True)
'''


def collect_replay_inputs():
    """Read old input provenance before considering any legacy force labels."""
    target = DEST / "legacy_inputs.jsonl"
    if target.exists():
        raise FileExistsError(target)
    old = json.loads(REPLAY.read_text(encoding="utf-8"))
    records = [{"sample_id": s["sample_id"], "source_directory": s["source_directory"]}
               for s in old["samples"]]
    current = json.loads((SOURCE / "collection_request.json").read_text())
    records += [{"sample_id": "current_" + r["name"], "source_directory": r["remote_dir"]}
                for r in current["records"]]
    code = "RECORDS=" + repr(records) + "\n" + REMOTE_INPUT_READER
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                             "sunboquan-codex", "python3 -"], input=code.encode(),
                            capture_output=True, timeout=150, check=False)
    DEST.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(result.stdout)
    with (DEST / "legacy_inputs.stderr.txt").open("xb") as handle:
        handle.write(result.stderr)
    write_json_exclusive(DEST / "legacy_collection_receipt.json", {
        "exit_code": result.returncode, "source_labels_sha256": sha256_file(REPLAY),
        "raw_inputs_sha256": sha256_file(target), "new_calculation": False,
        "status": "COLLECTED" if result.returncode == 0 else "FAILED_READ_ONLY_COLLECTION"})
    if result.returncode:
        raise RuntimeError("read-only input collection failed; preserved receipt")
    print(json.dumps({"input_records": len(result.stdout.splitlines()), "remote_write": False}))


def review_geometry():
    import numpy as np
    import yaml
    from ase.io import read

    from archive.fe110_five_c2_adsorption_20261006.build_supplement import equivalent_rmsd, surface_symmetries
    from scripts.adsorption.build_fe110_adsorption import read_poscar
    from scripts.adsorption.build_fe110_care_isomers import review

    target = DEST / "near_duplicate_review.json"
    if target.exists():
        raise FileExistsError(target)
    data = json.loads((SOURCE / "dataset_review.json").read_text())
    prior = json.loads((SOURCE / "geometry_split_review.json").read_text())
    if prior["source_dataset_sha256"] != sha256_file(SOURCE / "dataset_review.json") or not prior["all_geometry_pass"]:
        raise ValueError("prior geometry evidence changed or failed")
    seed_review = json.loads((BASE / "candidate_review.json").read_text())
    slab_path = ROOT / seed_review["slab"]
    if sha256_file(slab_path) != seed_review["slab_sha256"]:
        raise ValueError("slab changed")
    operations = surface_symmetries(read_poscar(slab_path))
    rules = yaml.safe_load((ROOT / "configs/adsmind_lite/analysis_rules.yaml").read_text())
    tolerance = rules["duplicate_detection"]["geometry_rmsd_tolerance_angstrom"]
    structures, sites = {}, []
    for sample in data["samples"]:
        path = SOURCE / sample["structure_path"]
        if sha256_file(path) != sample["structure_sha256"]:
            raise ValueError("structure changed")
        structure = read_poscar(path)
        structures[sample["sample_id"]] = structure
        initial = read_poscar(SOURCE / "sources" / sample["source_name"] / "POSCAR")
        result = review(initial, structure, list(range(45, len(structure.frac))))
        atoms = read(path, format="vasp")
        forces = np.asarray(sample["forces_eV_per_A"])
        sites.append({"sample_id": sample["sample_id"], "split": sample["split"],
                      "atomic_sites": result["atom_site_details"],
                      "movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max()),
                      "fixed_mask": [int(i) for i in atoms.constraints[0].get_indices()],
                      "chemistry_geometry": "PASS_FROM_BOUND_REVIEW", "final_minimum_acceptance": False})
    pairs = []
    for i, first in enumerate(data["samples"]):
        for second in data["samples"][i+1:]:
            # Different constitutional identities must never be collapsed by formula.
            if first["source_name"][:2] != second["source_name"][:2]:
                continue
            distance = equivalent_rmsd(structures[first["sample_id"]], structures[second["sample_id"]],
                                       operations, remove_height_shift=False)
            if distance <= tolerance:
                pairs.append({"first": first["sample_id"], "second": second["sample_id"],
                              "first_split": first["split"], "second_split": second["split"],
                              "adsorbate_symmetry_RMSD_A": distance})
    # Keep frozen heldout untouched. Development matching heldout cannot select epochs;
    # train matching either validation partition cannot receive gradients.
    priority = {"train": 0, "development": 1, "heldout": 2}
    exclusion = {}
    for pair in pairs:
        a, b = pair["first_split"], pair["second_split"]
        if a == b:
            continue
        lower = pair["first"] if priority[a] < priority[b] else pair["second"]
        higher = pair["second"] if lower == pair["first"] else pair["first"]
        exclusion.setdefault(lower, []).append(higher)
    retained = [s for s in data["samples"] if s["sample_id"] not in exclusion]
    # Within-split trajectory frames are not discarded just for a relaxed-state
    # .20 A similarity: materially different forces remain valuable labels.
    write_json_exclusive(target, {"source_dataset_sha256": sha256_file(SOURCE / "dataset_review.json"),
        "source_geometry_review_sha256": sha256_file(SOURCE / "geometry_split_review.json"),
        "slab_sha256": sha256_file(slab_path), "surface_operations": len(operations),
        "threshold_A": tolerance, "height_shift_removed": False,
        "metric": "adsorbate RMSD under clean-slab symmetry/xy PBC/H permutation; no Fe averaging or arbitrary rigid alignment",
        "policy": "conservative split isolation; near-duplicate is not an identical force label or proof of identical minimum",
        "near_pairs": pairs, "excluded_from_fit_or_epoch_selection": exclusion,
        "retained_counts": dict(Counter(s["split"] for s in retained)), "site_reviews": sites,
        "whole_job_splits_unchanged": True, "heldout_used_for_gradients_or_epoch_selection": False,
        "limitations": ["no independent unseen-species guarantee", "CH-C-O species03 has no completed labels",
                       "within-split near frames retained for force/stage coverage; correlated sample count is not independent sample count"]})
    print(json.dumps({"near_pairs": len(pairs), "excluded": len(exclusion),
                      "retained_counts": dict(Counter(s["split"] for s in retained))}))


def replay_compatibility():
    import numpy as np
    from ase.io import read
    from scripts.vasp_result_gate import read_incar_values

    target = DEST / "replay_compatibility.json"
    if target.exists():
        raise FileExistsError(target)
    receipt = json.loads((DEST / "legacy_collection_receipt.json").read_text())
    if receipt["exit_code"] != 0 or receipt["raw_inputs_sha256"] != sha256_file(DEST / "legacy_inputs.jsonl"):
        raise ValueError("raw source binding failed")
    raw = [json.loads(line) for line in (DEST / "legacy_inputs.jsonl").read_text().splitlines()]
    old = {s["sample_id"]: s for s in json.loads(REPLAY.read_text())["samples"]}
    expected = json.loads((SOURCE / "collection_request.json").read_text())["records"]
    potcars = {}
    for r in raw:
        if r["sample_id"].startswith("current_"):
            e = next(x for x in expected if "current_" + x["name"] == r["sample_id"])
            if r["POTCAR"]["sha256"] != e["potcar_sha256"]:
                raise ValueError("current POTCAR changed")
            for block in r["POTCAR"]["blocks"]:
                prior = potcars.setdefault(block["titel"], block["sha256"])
                if prior != block["sha256"]:
                    raise ValueError("current POTCAR family inconsistency")
    reference = read(SOURCE / "sources/01_cfg1/POSCAR", format="vasp")
    records = []
    for r in raw:
        if r["sample_id"] not in old:
            continue
        sample = old[r["sample_id"]]
        folder = DEST / "legacy_sources" / r["sample_id"]
        folder.mkdir(parents=True, exist_ok=True)
        missing = []
        for name, blob in r["files"].items():
            if blob.get("missing"):
                missing.append(name)
                continue
            data = base64.b64decode(blob["base64"], validate=True)
            preserve_bytes(folder / name, data)
            if sha256_file(folder / name) != blob["sha256"]:
                raise ValueError("copied input hash changed")
        if missing:
            records.append({"sample_id": r["sample_id"], "compatible_inputs": False, "missing": missing})
            continue
        incar = read_incar_values(folder / "INCAR")
        atoms = read(folder / "CONTCAR", format="vasp")
        initial = read(folder / "POSCAR", format="vasp")
        fixed = [int(i) for i in atoms.constraints[0].get_indices()] if atoms.constraints else []
        numeric = {"ENCUT": 400, "EDIFF": 1e-5, "EDIFFG": -.02, "ISPIN": 2, "ISMEAR": 1, "SIGMA": .2, "ISYM": 0}
        checks = {k: k in incar and np.isclose(float(incar[k]), v, rtol=0, atol=1e-12) for k, v in numeric.items()}
        checks.update(GGA=incar.get("GGA") == "PE", LDIPOL=str(incar.get("LDIPOL")).upper() in {".FALSE.", "FALSE", "F"},
            same_cell=np.allclose(atoms.cell, reference.cell, rtol=0, atol=1e-8),
            fixed_mask=fixed == list(range(18)),
            fixed_coordinates=np.allclose(atoms.positions[:18], reference.positions[:18], rtol=0, atol=1e-8),
            slab_Fe45=atoms.get_chemical_symbols()[:45] == ["Fe"]*45,
            preserved_order=atoms.get_chemical_symbols() == initial.get_chemical_symbols() == sample["symbols"],
            structure_hash=sha256_file(folder / "CONTCAR") == sample["structure_sha256"],
            same_POTCAR=all(potcars.get(b["titel"]) == b["sha256"] for b in r["POTCAR"].get("blocks", [])) and not r["POTCAR"].get("missing"))
        kp = (folder / "KPOINTS").read_text().splitlines()
        checks["kmesh"] = len(kp) >= 5 and kp[2].strip().lower().startswith("g") and kp[3].split() == ["5", "5", "1"] and all(float(v) == 0 for v in kp[4].split())
        mag = expand_magmom(incar.get("MAGMOM", ""))
        checks["magnetic_seed"] = len(mag) == len(atoms) and np.allclose(mag[:45], 2.2) and np.allclose(mag[45:], 0)
        checks = {key: bool(value) for key, value in checks.items()}
        records.append({"sample_id": r["sample_id"], "compatible_inputs": all(checks.values()),
                        "checks": checks, "SIGMA_eV": float(incar["SIGMA"]), "POTCAR": r["POTCAR"],
                        "input_files": {name: blob.get("sha256") for name, blob in r["files"].items()},
                        "force_source_verified": False, "training_eligible": False})
    write_json_exclusive(target, {"records": records, "source_labels_sha256": sha256_file(REPLAY),
        "input_collection_sha256": sha256_file(DEST / "legacy_inputs.jsonl"),
        "approved_current_species_POTCAR_blocks": potcars,
        "compatible_input_count": sum(r["compatible_inputs"] for r in records),
        "scope": "force-label compatibility; not adsorption energy reference compatibility"})
    print(json.dumps({"compatible_inputs": sum(r["compatible_inputs"] for r in records),
                      "failures": {r["sample_id"]: [k for k, v in r.get("checks", {}).items() if not v]
                                   for r in records if not r["compatible_inputs"]}}))


def expand_magmom(value):
    mag = []
    for token in str(value).split():
        if "*" in token:
            count, moment = token.split("*")
            mag.extend([float(moment)]*int(count))
        else:
            mag.append(float(token))
    return mag


def collect_replay_labels():
    target = DEST / "legacy_force_sources.jsonl"
    if target.exists():
        raise FileExistsError(target)
    review = json.loads((DEST / "replay_compatibility.json").read_text())
    eligible = {r["sample_id"] for r in review["records"] if r["compatible_inputs"]}
    records = [s for s in json.loads(REPLAY.read_text())["samples"] if s["sample_id"] in eligible]
    code = "RECORDS=" + repr(records) + "\n" + REMOTE_LABEL_READER
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
                             "sunboquan-codex", "python3 -"], input=code.encode(),
                            capture_output=True, timeout=180, check=False)
    with target.open("xb") as handle:
        handle.write(result.stdout)
    with (DEST / "legacy_force_sources.stderr.txt").open("xb") as handle:
        handle.write(result.stderr)
    write_json_exclusive(DEST / "legacy_force_collection_receipt.json", {
        "exit_code": result.returncode, "raw_sources_sha256": sha256_file(target), "new_calculation": False})
    if result.returncode:
        raise RuntimeError("legacy label collection failed; preserved receipt")
    print(json.dumps({"collected_force_sources": len(result.stdout.splitlines()), "new_VASP": False}))


def validate_replay_labels():
    import numpy as np
    from ase.io import read
    from archive.fe110_five_c2_adsorption_20261006.prepare_c2_force_diagnostic import verify_frame
    from scripts.neb_agent.utils_vasp import parse_oszicar
    from scripts.vasp_result_gate import read_incar_values

    target = DEST / "replay_labels.reviewed.json"
    if target.exists():
        raise FileExistsError(target)
    receipt = json.loads((DEST / "legacy_force_collection_receipt.json").read_text())
    if receipt["exit_code"] != 0 or receipt["raw_sources_sha256"] != sha256_file(DEST / "legacy_force_sources.jsonl"):
        raise ValueError("force source receipt mismatch")
    compatibility = json.loads((DEST / "replay_compatibility.json").read_text())
    eligible = {r["sample_id"] for r in compatibility["records"] if r["compatible_inputs"]}
    old = {s["sample_id"]: s for s in json.loads(REPLAY.read_text())["samples"]}
    samples = []
    for line in (DEST / "legacy_force_sources.jsonl").read_text().splitlines():
        r = json.loads(line)
        sid = r["sample_id"]
        if sid not in eligible or not all(r[k] for k in ("normal_footer", "required_accuracy", "EDIFF_marker_before_force")):
            raise ValueError("replay label source failed")
        folder = DEST / "legacy_sources" / sid
        atoms = read(folder / "CONTCAR", format="vasp")
        if sha256_file(folder / "CONTCAR") != old[sid]["structure_sha256"]:
            raise ValueError("replay geometry changed")
        forces = verify_frame(atoms, r)
        if not np.array_equal(forces, np.asarray(old[sid]["forces_eV_per_A"])) or r["toten_eV"] != old[sid]["final_toten_eV"]:
            raise ValueError("old force/energy labels differ from source")
        for name, raw in (("OSZICAR", r["OSZICAR_base64"]), ("final_force_table.txt", r["force_table_base64"])):
            with (folder / name).open("xb") as handle:
                handle.write(base64.b64decode(raw, validate=True))
        osz = parse_oszicar(folder / "OSZICAR")
        incar = read_incar_values(folder / "INCAR")
        cycle = osz["electronic_cycles"][-1]
        if (cycle["iteration"] != r["electronic_iteration"] or cycle["ionic_step"] != r["ionic_step"]
                or cycle["iteration"] >= int(incar["NELM"]) or abs(osz["energies"][-1] - r["toten_eV"]) > 1e-4):
            raise ValueError("replay final SCF association failed")
        atoms.pbc = [True, True, False]
        distances = atoms.get_all_distances(mic=True)
        np.fill_diagonal(distances, np.inf)
        if distances.min() < .80:
            raise ValueError("replay collision")
        samples.append({**old[sid], "source_OUTCAR_sha256": r["OUTCAR_sha256"],
            "source_force_table_sha256": sha256_file(folder / "final_force_table.txt"),
            "ionic_step": r["ionic_step"], "electronic_converged": True,
            "geometry_review_pass": True, "minimum_pair_distance_A": float(distances.min()),
            "final_movable_fmax_eV_A": float(np.linalg.norm(forces[18:], axis=1).max()),
            "training_eligible_after_user_package_review": True,
            "compatibility_review_sha256": sha256_file(DEST / "replay_compatibility.json")})
    write_json_exclusive(target, {"samples": samples, "force_source_collection_sha256": receipt["raw_sources_sha256"],
        "old_labels_sha256": sha256_file(REPLAY), "reportable_final_energy": False,
        "role": "compatible adsorption retention labels; not unseen-species generalization evidence"})
    print(json.dumps({"verified_replay_labels": len(samples), "new_calculation": False}))


def select_temporal_frames(samples, near):
    import numpy as np

    within_exclusions, kept = {}, []
    for sample in sorted(samples, key=lambda s: (s["source_name"], -s["ionic_step"])):
        if sample["sample_id"] in near["excluded_from_fit_or_epoch_selection"]:
            continue
        redundant = None
        if sample["split"] != "heldout":
            for previous in kept:
                if sample["source_name"] != previous["source_name"]:
                    continue
                pair = next((p for p in near["near_pairs"] if {p["first"], p["second"]} == {sample["sample_id"], previous["sample_id"]}), None)
                maximum = float(np.linalg.norm(np.asarray(sample["forces_eV_per_A"])[18:] - np.asarray(previous["forces_eV_per_A"])[18:], axis=1).max())
                if pair and maximum <= .02:
                    redundant = {"representative": previous["sample_id"], "max_force_difference_eV_A": maximum,
                                 "symmetry_RMSD_A": pair["adsorbate_symmetry_RMSD_A"]}
                    break
        if redundant:
            within_exclusions[sample["sample_id"]] = redundant
        else:
            kept.append(sample)
    return kept, within_exclusions


def cross_split_near_pairs(splits, operations, threshold):
    from archive.fe110_five_c2_adsorption_20261006.build_supplement import equivalent_rmsd
    from scripts.neb_agent.utils_structure import read_poscar

    pairs = []
    for a, first in enumerate(splits):
        for second in list(splits)[a+1:]:
            for x in splits[first]:
                for y in splits[second]:
                    if x["symbols"] != y["symbols"]:
                        continue
                    distance = equivalent_rmsd(read_poscar(DEST / x["structure_path"]), read_poscar(DEST / y["structure_path"]), operations, remove_height_shift=False)
                    if distance <= threshold:
                        pairs.append([x["sample_id"], y["sample_id"], distance])
    return pairs


def prepare_package():
    import yaml
    from scripts.adsorption.force_finetune import build_database, verify_request
    from scripts.matris_training_exclusions import structure_equivalence_fingerprint
    from scripts.neb_agent.utils_structure import read_poscar

    target = DEST / "training_request.json"
    if target.exists() or (DEST / "training_manifest.json").exists():
        raise FileExistsError("package is immutable; inspect existing preparation")
    data = json.loads((SOURCE / "dataset_review.json").read_text())
    geometry = json.loads((SOURCE / "geometry_split_review.json").read_text())
    near = json.loads((DEST / "near_duplicate_review.json").read_text())
    excluded = near["excluded_from_fit_or_epoch_selection"]
    replay = json.loads((DEST / "replay_labels.reviewed.json").read_text())
    reviewed = {s["sample_id"]: s for s in geometry["records"]}
    splits = {s: [] for s in ("train", "development", "heldout")}
    artifacts = []

    def copy(source, relative):
        destination = DEST / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != source.read_bytes():
                raise ValueError("partial package artifact changed")
        else:
            shutil.copyfile(source, destination)
        artifacts.append(destination)
        return relative

    copy(SOURCE / "dataset_review.json", "evidence/trajectory_labels.json")
    copy(SOURCE / "geometry_split_review.json", "evidence/geometry_split_review.json")
    # Near-final temporal copies should not overweight the same minimum.
    # .02 eV/A is a data-redundancy review tolerance, not a new physics gate.
    kept, within_exclusions = select_temporal_frames(data["samples"], near)
    for sample in kept:
        path = copy(SOURCE / sample["structure_path"], "structures/" + sample["sample_id"] + ".vasp")
        current = {k: v for k, v in sample.items() if k not in {"chemistry_review", "training_eligible"}}
        splits[sample["split"]].append({**current, "structure_path": path,
            "chemistry_review": "PASS_BOUND_GEOMETRY_AND_CONNECTIVITY_REVIEW",
            "training_state": "PREPARED_PENDING_USER_AUTHORIZATION",
            "structure_equivalence_sha256": reviewed[sample["sample_id"]]["structure_equivalence_sha256"],
            "geometry_review_pass": reviewed[sample["sample_id"]]["geometry_pass"],
            "energy_eV_force_label_only": sample["toten_eV_force_label_only"],
            "calculation_group": "current_vasp_job_" + sample["source_job_id"],
            "sample_role": "adsorption_trajectory_" + sample["split"],
            "label_source": {"path": "evidence/trajectory_labels.json", "sha256": sha256_file(SOURCE / "dataset_review.json"), "sample_id": sample["sample_id"]}})
    replay_development = {"h2_top", "ch2_top", "ch2o_oend_top", "c2o_hlbh"}
    for sample in replay["samples"]:
        sid = sample["sample_id"]
        path = copy(DEST / "legacy_sources" / sid / "CONTCAR", "structures/replay_" + sid + ".vasp")
        split = "development" if sid in replay_development else "train"
        splits[split].append({"sample_id": "replay_" + sid, "structure_path": path,
            "structure_sha256": sample["structure_sha256"], "symbols": sample["symbols"],
            "fixed_atom_indices_0based": list(range(18)), "forces_eV_per_A": sample["forces_eV_per_A"],
            "energy_eV_force_label_only": sample["final_toten_eV"], "ionic_step": sample["ionic_step"],
            "structure_equivalence_sha256": structure_equivalence_fingerprint(read_poscar(DEST / path)),
            "electronic_converged": True, "geometry_review_pass": True,
            "calculation_group": "legacy_vasp_directory_" + sid,
            "source_OUTCAR_sha256": sample["source_OUTCAR_sha256"], "sample_role": "adsorption_retention_" + split,
            "label_source": {"path": "replay_labels.reviewed.json", "sha256": sha256_file(DEST / "replay_labels.reviewed.json"), "sample_id": sid}})
    # Legacy replay can only be compared when composition/order matches. The
    # current C2H/C2H2/C2HO labels do not share composition with these old rows.
    from archive.fe110_five_c2_adsorption_20261006.build_supplement import surface_symmetries
    seed_review = json.loads((BASE / "candidate_review.json").read_text())
    operations = surface_symmetries(read_poscar(ROOT / seed_review["slab"]))
    cross_pairs = cross_split_near_pairs(splits, operations, near["threshold_A"])
    if cross_pairs:
        raise ValueError("replay/current cross-split near duplicates remain: " + repr(cross_pairs))
    write_json_exclusive(DEST / "selection_review.json", {
        "near_review_sha256": sha256_file(DEST / "near_duplicate_review.json"),
        "cross_split_exclusions": excluded, "within_job_redundant_force_frames": within_exclusions,
        "within_job_force_difference_tolerance_eV_A": .02, "near_threshold_A": near["threshold_A"],
        "heldout_untouched": True, "replay_development": sorted(replay_development),
        "cross_split_near_duplicates_after_replay": cross_pairs,
        "counts": {s: len(rows) for s, rows in splits.items()}})
    manifest = {"document_kind": "aqcat25_adsorption_force_training_manifest", "schema_version": 1,
        "training_target": "forces_only", "energy_loss_coefficient": 0, "reportable_final_energy": False,
        "splits": splits, "intermediate_frames_are_accepted_endpoints": False,
        "heldout_role": "unseen whole-job validation only; no gradient or epoch choice",
        "CHCO_species03_supported": False}
    write_json_exclusive(DEST / "training_manifest.json", manifest)
    artifacts.extend([DEST / "training_manifest.json", DEST / "selection_review.json"])
    for name in ("near_duplicate_review.json", "replay_compatibility.json", "replay_labels.reviewed.json",
                 "legacy_force_sources.jsonl", "legacy_force_collection_receipt.json", "legacy_inputs.jsonl", "legacy_collection_receipt.json"):
        artifacts.append(DEST / name)
    for source in (ROOT / "scripts/adsorption/force_finetune.py", ROOT / "scripts/adsorption/adsorption_finetune_job.sh"):
        copy(source, "runtime/" + source.name)
    copy(BASE / "gpu_repair_v1/runtime/aqcat25_mz73_env.sh", "runtime/aqcat25_mz73_env.sh")
    template = Path("C:/Users/86177/Desktop/机器学习/aqcat25_ts_pilot/force_only_config.yml")
    config = yaml.safe_load(template.read_text())
    remote = "/home/sbq/sbq/adsorption_c2_finetune_20261010_" + DEST.name.rsplit("_", 1)[-1]
    train = config["dataset"]["train"]
    train.update(format="ase_db", src=remote + "/train.db", seed=42,
                 atoms_transform_args={"skip_always": True})
    config["dataset"]["val"] = {**train, "src": remote + "/development.db"}
    config["checkpoint"] = remote + "/output/job_warmstart.pt"
    config["optim"].update(max_epochs=4, lr_initial=1e-5, load_best=True)
    config["optim"]["scheduler_params"].update(epochs=4, lr=1e-5)
    config["seed"] = 42
    with (DEST / "config.yml").open("x", encoding="utf-8", newline="\n") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)
    artifacts.append(DEST / "config.yml")
    for split in splits:
        path = DEST / (split + ".db")
        build_database(DEST / "training_manifest.json", path, split)
        artifacts.append(path)
    request = {"schema_version": 1, "document_kind": "aqcat25_adsorption_small_finetune_request",
        "status": "PREPARED_FOR_USER_REVIEW_NOT_SUBMITTED", "training_authorized": False,
        "manifest_path": "training_manifest.json", "config_path": "config.yml", "remote_package_root": remote,
        "split_counts": {s: len(rows) for s, rows in splits.items()},
        "base_checkpoint": {"path": "/home/sbq/sbq/aqcat25/demo_single/model.pt",
            "sha256": "e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50"},
        "training_limits": {"epochs": 4, "learning_rate": 1e-5, "seed": 42, "batch_size": 1,
            "GPU_count": 1, "CPU_count": 4, "memory_GB": 32, "walltime_minutes": 30,
            "baseline_optimizer_and_epoch_restored": False, "unattended_retries": 0},
        "candidate_checks": ["same-structure baseline/candidate comparison grouped movableFe/C/O/H/adsorbate and near-minimum frames",
            "retention development vs C2 development separately; do not use overall Fe-dominated MAE as sole promotion criterion",
            "evaluate frozen whole-job heldout once after candidate chosen; not used to select epoch",
            "bounded near-minimum drift test must be separately reviewed before VASP benchmark"],
        "promotion": "none automatic; checkpoint is force-pre-relax candidate only, not calibrated energy-ranking model",
        "speedup_claim": "not established; paired VASP step/time and full GPU/training cost benchmark required",
        "remaining_before_submission": ["user reviews and separately authorizes this exact request hash",
            "MZ73 no-training runtime/checkpoint/config preflight and available GPU check"],
        "artifacts": [{"path": p.relative_to(DEST).as_posix(), "sha256": sha256_file(p)} for p in sorted(set(artifacts))]}
    write_json_exclusive(target, request)
    print(json.dumps(verify_request(target)))


def record_package():
    from scripts.adsorption.force_finetune import verify_request
    from scripts.state_manager.models import validate_event

    verify_request(DEST / "training_request.json")
    previous = "task-fe110-c2-acceleration-adjustment-prepared-20261010"
    event = json.loads((ROOT / "modules/state_handoff/events" / (previous + ".json")).read_text())
    event_id = "task-fe110-c2-adsorption-finetune-review-ready-20261010"
    target = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    now = datetime.now(timezone.utc).isoformat()
    paths = [DEST / n for n in ("training_request.json", "training_manifest.json", "selection_review.json",
                               "replay_compatibility.json", "replay_labels.reviewed.json")]
    paths += [ROOT / "docs/reviews/fe110_adsorption_finetune_package_20261010.md",
              ROOT / "scripts/adsorption/force_finetune.py", ROOT / "scripts/adsorption/adsorption_finetune_job.sh",
              Path(__file__).resolve()]
    event.update(event_id=event_id, occurred_at=now, recorded_at=now, supersedes=[previous],
        summary="Prepare reviewed-source adsorption force fine-tuning package with near-duplicate exclusion, compatible replay and bounded separate-authorization GPU request; no training submitted.",
        evidence=[{"locator": p.relative_to(ROOT).as_posix(), "sha256": sha256_file(p), "authority": "module_validation", "observed_at": now} for p in paths])
    event["payload"].update(
        current_evidence=[
            "56 frozen C2 frames reviewed using36surface symmetries/xyPBC/Hpermutation/actual height;5train frames near heldout removed and2 redundant temporal force frames represented by final steps.",
            "13old adsorption replay sources compatible with active SIGMA0.20/Gamma5x5x1/Fe45/fixed0-17/POTCAR/magnetic branch; exact final force/TOTEN,SCF,normal-completion and printed-coordinate checks passed.",
            "Final v3 package:train34(25C2+9replay),development12(8C2+4replay),frozenheldout16. Cross-split near duplicates absent; actual ASE DB counts match;80artifact bindings valid.",
            "Adsorption-only adapter preserves source force/geometry and fixed masks; training uses4epochs/lr1e-5/seed42/1GPU/30min, rejects stale or missing separate authorization. No training or new VASP submitted.",
            "Pythoncompile,Ruff,bash-n and33targeted tests passed. MZ73 CPU baseline inspection only; complete GPU training/runtime chain and speedup not yet tested.",
            "species03 CHCO coverage remains absent; local preparation does not recheck current CHCO job status or mutate jobs. No checkpoint or accepted energy promoted."
        ],
        one_executable_step="Review v3 request SHA2e1b517270395b414c8e7079cf95df93656014e24ce2db3f1e6b5e0ac3c40d16 and separately authorize one bounded adsorption GPU fine-tuning run; only then perform MZ73 package/runtime preflight and submit.",
        submission_boundary="Review-ready only. No new GPU/VASP submission, model promotion, job stop, DFT parameter change or automatic retry authorized.",
        authoritative_references=["configs/execution_backends.yaml", "modules/adsorption_workflow/README.md", "configs/true_fe110_production.yaml"] + [p.relative_to(ROOT).as_posix() for p in paths])
    validate_event(event)
    write_json_exclusive(target, event)
    print(target.relative_to(ROOT).as_posix())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    actions = {"collect-replay-inputs": collect_replay_inputs, "review-geometry": review_geometry,
               "replay-compatibility": replay_compatibility, "collect-replay-labels": collect_replay_labels,
               "validate-replay-labels": validate_replay_labels, "prepare-package": prepare_package,
               "record-package": record_package}
    parser.add_argument("action", choices=actions)
    parser.add_argument("--destination-name", default=DEST.name)
    args = parser.parse_args()
    if Path(args.destination_name).name != args.destination_name or not args.destination_name.startswith("adsorption_finetune_review_"):
        raise ValueError("unsafe package directory")
    DEST = BASE / args.destination_name
    actions[args.action]()
