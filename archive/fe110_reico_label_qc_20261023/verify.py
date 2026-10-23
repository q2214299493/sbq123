"""Independently verify force bins and enumerate atom mappings for real pairs."""
from __future__ import annotations

from itertools import permutations, product
from pathlib import Path

import numpy as np
from ase.geometry import find_mic
from ase.io import read

from archive.fe110_reico_label_qc_20261023.collect import OUTPUT
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest_valid, write_json


def verify_pairs(rows: dict, pairs: list) -> list:
    results=[]
    for pair in pairs:
        one,two=rows[pair["first"]],rows[pair["second"]]
        first,second=read(one["structure_path"],format="vasp"),read(two["structure_path"],format="vasp")
        symbols=first.get_chemical_symbols()
        groups=[[i for i in range(45,len(first)) if symbols[i]==s] for s in sorted(set(symbols[45:]))]
        cost_best=float("inf")
        mapping_best=None
        for variant in product(*(permutations(group) for group in groups)):
            mapping=list(range(len(first)))
            for group,permutation in zip(groups,variant,strict=True):
                for i,j in zip(group,permutation,strict=True):
                    mapping[i]=j
            _,distances=find_mic(first.positions[45:]-second.positions[np.asarray(mapping)[45:]],first.cell,[True,True,False])
            cost=float(np.sum(distances**2))
            if cost < cost_best:
                cost_best,mapping_best=cost,mapping
        _,fe=find_mic(first.positions[18:45]-second.positions[18:45],first.cell,[True,True,False])
        distance=max(np.sqrt(cost_best/(len(first)-45)),np.sqrt(np.mean(fe**2)))
        assert abs(distance-pair["geometry_RMSD_A"]) < 1e-12
        delta=np.asarray(two["forces_eV_per_A"])[mapping_best]-np.asarray(one["forces_eV_per_A"])
        metric=float(np.sqrt(np.mean(np.sum(delta[45:]**2,axis=1))))
        assert abs(metric-pair["adsorbate"]["vector_RMSE_difference_eV_A"]) < 1e-12
        worst=int(np.argmax(np.linalg.norm(delta[45:],axis=1)))+45
        first.pbc=second.pbc=[True,True,False]
        neighbors=sorted((i for i in range(len(first)) if i!=worst),key=lambda i:first.get_distance(worst,i,mic=True))[:3]
        results.append({"first":pair["first"],"second":pair["second"],"enumerated_mapping_and_metric_match":True,
                        "largest_change_atom_1based":worst+1,"element":symbols[worst],
                        "nearest_contacts_A":[{"neighbor_1based":j+1,"element":symbols[j],
                                                "first":first.get_distance(worst,j,mic=True),
                                                "second":second.get_distance(mapping_best[worst],mapping_best[j],mic=True)} for j in neighbors]})
    return results


def main():
    summary=load_json_object(OUTPUT/"review_summary.json")
    assert source_file_manifest_valid(summary)
    rows=load_json_object(OUTPUT/"all_label_qc_local_only.json")["samples"]
    for row in rows:
        path=Path(row["structure_path"]).parent
        assert all(sha256_file(path/name)==digest for name,digest in row["input_output_hashes"].items())
    train={r["sample_id"]:r for r in rows if r["partition"]=="train" and r["data_qc_status"]=="PASS"}
    assert len(train)==summary["training_labels_analyzed"]
    for composition,coverage in summary["training_force_coverage"].items():
        values=[float(np.linalg.norm(np.asarray(r["forces_eV_per_A"])[18:],axis=1).max()) for r in train.values() if r["composition"]==composition]
        assert len(values)==coverage["frames"]
        for interval,count in coverage["movable_fmax_histogram"].items():
            lower,upper=map(float,interval[1:-1].split(","))
            assert sum(lower<=v<upper for v in values)==count
    pairs=load_json_object(OUTPUT/"nearby_training_pairs.json")["pairs"]
    assert all(p["first"] in train and p["second"] in train for p in pairs)
    details=verify_pairs(train,pairs)
    result={"status":"PASS","label_source_hashes_verified":len(rows),"training_only_analysis":True,
            "permutation_enumerated_pairs":len(details),"pair_checks":details,
            "summary_sha256":sha256_file(OUTPUT/"review_summary.json"),"new_DFT_or_training":False}
    write_json(OUTPUT/"independent_verification.json",result)
    print({"status":"PASS","labels":len(rows),"independent_pairs":len(details)})


if __name__ == "__main__":
    main()
