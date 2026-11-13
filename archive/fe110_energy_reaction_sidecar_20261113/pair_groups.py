"""Identify conservative same-family energy pairs; no paired training data written."""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, source_file_manifest, write_json_exclusive
from .collect import OUT


def run():
    rows = load_json_object(OUT / "energy_label_sidecar_final_v2.json")["records"]
    catalog = load_json_object(OUT / "energy_reuse_catalog_v2.json")["records"]
    allowed = {r["physical_label_key"]: r for r in catalog if r["raw_E_F_local_magnetic_evidence_ready"]}
    index = load_json_object(OUT / "raw_source_index.json")["entries"]
    remote = {}
    for name in ("remote_raw_evidence.json", "remote_additional_evidence.json"):
        remote.update({r["OUTCAR_sha256"]: r for r in load_json_object(OUT / name)["results"] if r.get("expected_hash_matches")})
    unique = {}
    for row in rows:
        key = row.get("physical_label_key")
        if key in allowed and row.get("energy_force_evidence_ready_for_review"):
            unique.setdefault(key, row)
    groups = defaultdict(list)
    evidence_paths = []
    for key, row in unique.items():
        digest = row["source_OUTCAR_sha256"]
        signature = {"same_OUTCAR": digest}
        if row.get("family_id"):
            inc = kp = pot = None
            if digest in remote:
                inc = remote[digest]["input_sha256"].get("INCAR")
                kp = remote[digest]["input_sha256"].get("KPOINTS")
                pot = remote[digest].get("POTCAR_sha256")
            else:
                source = next((r for r in index.get(digest, []) if r.get("POTCAR_sha256") and all(Path(r["paths"].get(n, "missing")).is_file() for n in ("INCAR", "KPOINTS"))), None)
                if source:
                    inc, kp = [sha256_file(Path(source["paths"][n])) for n in ("INCAR", "KPOINTS")]
                    pot = source["POTCAR_sha256"]
                    evidence_paths.extend(Path(source["paths"][n]) for n in ("INCAR", "KPOINTS"))
            if inc and kp and pot:
                signature = {"family_id": row["family_id"], "composition": row["composition"],
                             "INCAR_sha256": inc, "KPOINTS_sha256": kp, "POTCAR_sha256": pot,
                             "cell_and_fixed_mask": "already_raw_verified_Fe45_same_cell_bottom18"}
        groups[sha256_json(signature)].append({"physical_key": key, "sample_id": row["sample_id"],
                                               "E_TOTEN_eV": row["E_TOTEN_eV"],
                                               "future_training_candidate": allowed[key]["future_energy_reuse_review_candidate"],
                                               "signature": signature})
    summaries = [{"group_id": group, "members": members, "physical_frames": len(members),
                  "same_physics_pairs_available": len(members) > 1,
                  "training_eligible_scope_after_review": all(m["future_training_candidate"] for m in members),
                  "anchor_is_not_an_IS_or_stability_claim": True}
                 for group, members in groups.items()]
    write_json_exclusive(OUT / "relative_energy_pair_candidates.json", {
        "status": "PAIRING_EVIDENCE_ONLY_NOT_TRAINING_LABELS", "groups": summaries,
        "criterion": "same_trajectory_or_same_family_identical_INCAR_KPOINTS_POTCAR_and_verified_cell_mask",
        "singly_labelled_groups_not_a_reason_for_duplicate_DFT": True,
        "source_files": source_file_manifest([OUT / "energy_label_sidecar_final_v2.json", OUT / "energy_reuse_catalog_v2.json",
                                              OUT / "raw_source_index.json", OUT / "remote_raw_evidence.json",
                                              OUT / "remote_additional_evidence.json", Path(__file__), *evidence_paths])})
    print({"pair_groups": sum(r["same_physics_pairs_available"] for r in summaries),
           "train_pair_groups": sum(r["same_physics_pairs_available"] and r["training_eligible_scope_after_review"] for r in summaries),
           "paired_frames": sum(r["physical_frames"] for r in summaries if r["same_physics_pairs_available"])})


if __name__ == "__main__":
    run()
