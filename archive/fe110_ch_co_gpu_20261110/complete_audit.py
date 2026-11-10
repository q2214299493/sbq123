"""Finish only the authorized exact-path audit, never repeat primary NEB steps."""
from pathlib import Path
import json
import shutil

from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.aqcat25_handoff import atom_order_sha256, validate_handoff
from scripts.adsorption.build_fe110_adsorption import read_poscar,expanded_symbols
from scripts.dual_model_ml_neb import _load_request, _load_images, _geometry_guard_evidence
from . import prepare, transport


def main():
    parent=prepare.OUT
    root=parent.parent/"gpu_fixed_path_audit_20261110_v2"
    remote="/home/sbq/sbq/fe110_ch_co_fixed_path_audit_20261110_v2"
    if root.exists():
        raise SystemExit("Preserve the existing exact-path audit request.")
    returned=parent/"return_12405"
    if load_json_object(returned/"output/ml_neb_state.json")["converged"] is not True:
        raise ValueError("Primary parent is not a completed converged path.")
    receipt=load_json_object(returned/"collection_receipt.json")
    for item in receipt["files"]:
        if sha256_file(returned/item["path"])!=item["sha256"]:
            raise ValueError("Preserved primary path changed.")
    root.mkdir()
    package=root/"package"
    package.mkdir()
    original=load_json_object(parent/"package/request.json")
    request={**original,"request_id":"fe110_ch_co_exact_complete_audit_20261110_v2",
             "run_kind":"exact_fixed_path_audit_no_optimization",
             "ordinary_ml_neb":{**original["ordinary_ml_neb"],"max_steps":0},
             "resources":{**original["resources"],"wall_seconds":300},
             "primary_path_origin":{"gpu_job_id":"12405","primary_NEB_steps":60,
                 "parent_request_sha256":sha256_file(parent/"package/request.json"),
                 "parent_return_receipt_sha256":sha256_file(returned/"collection_receipt.json"),
                 "reason":"Complete authorized AQCat25 audit after explicit CPU=False loader repair; no primary path rerun."}}
    images=[]
    for index in range(7):
        label=f"{index:02d}"
        target=package/"images"/(label+".vasp")
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(returned/"output/ordinary/images"/label/"POSCAR",target)
        images.append({"image":label,"path":target.relative_to(package).as_posix(),"sha256":sha256_file(target)})
    request["images"]=images
    contract=prepare.PARENT/"reaction_contract.json"
    shutil.copyfile(contract,package/"reaction_contract.normalized.json")
    request["reaction"]={**request["reaction"],"normalized_reaction_contract":{"path":"reaction_contract.normalized.json","sha256":sha256_file(contract)}}
    symbols=expanded_symbols(read_poscar(package/images[0]["path"]))
    def ref(index):
        return {"path":images[index]["path"],"sha256":images[index]["sha256"],"format":"vasp_poscar","atom_count":len(symbols),"atom_order_sha256":atom_order_sha256(symbols)}
    handoff={"schema_version":2,"direction":"work_to_gpu","handoff_id":"fe110-ch-co-exact-path-audit-20261110",
        "workflow_kind":"transition_state","source_workflow_sha256":sha256_file(returned/"collection_receipt.json"),
        "candidate_structure":ref(3),"compatibility":{"branch":"true_fe110_5layer_5x5x1","sha256":request["reaction"]["compatibility_sha256"],"slab_model":"fe45_bottom18_fixed","facet":"Fe(110)"},
        "model":{"identifier":"MatRIS-primary/AQCat25-exact-audit","checkpoint_sha256":request["models"]["secondary"]["checkpoint_sha256"],"fmax_eV_per_A":.1,"max_steps":1},
        "selective_dynamics":{"fixed_atom_indices_1based":list(range(1,19)),"free_atom_count":31},
        "transition_state":{"normalized_reaction_contract_sha256":request["reaction"]["contract_sha256"],"atom_map_sha256":request["reaction"]["atom_map_sha256"],
            "initial_structure":ref(0),"waypoint_structures":[],"final_structure":ref(6),"indexed_bond_changes":request["reaction"]["indexed_bond_changes"]},
        "restrictions":{"predicted_candidate_only":True,"submit_vasp":False,"scientific_acceptance":False,"direct_gpu_to_vasp_handoff":False}}
    write_json_exclusive(package/"work_to_gpu.handoff.json",handoff)
    validate_handoff(package/"work_to_gpu.handoff.json",root=package)
    write_json_exclusive(package/"request.json",request)
    request_sha=sha256_file(package/"request.json")
    req=_load_request(package/"request.json")
    geometry=_geometry_guard_evidence(_load_images(req,package),req)
    if not geometry["passed"]:
        raise ValueError("Returned path fails geometry; do not run the audit.")
    write_json_exclusive(root/"local_geometry_preflight.json",geometry)
    for name in ["dual_model_ml_neb.py","aqcat25_ml_neb.py","aqcat25_handoff.py","artifact_io.py","mlip_same_structure_benchmark.py","ml_sella_candidate.py"]:
        shutil.copyfile(prepare.ROOT/"scripts"/name,package/name)
    for name in ("device.py","worker.py"):
        shutil.copyfile(parent/"package"/name,package/name)
    write_json_exclusive(package/"authorization.json",{"user_authorized":True,"request_sha256":request_sha,
        "user_request":"然后过渡态任务提交gpu和vasp","source_authorization":str(prepare.ROOT/"docs/reviews/fe110_c2_completion_20261110_user_authorization.md"),
        "scope":"Finish original exact seven-image audit only:zero NEB/CI/relaxation/training steps;one GPU<=300s;no VASP from GPU host."})
    script=(parent/"package/run.sbatch").read_text().replace(prepare.REMOTE,remote).replace("00:15:00","00:05:00").replace("fe110-ch-co-ml-neb","fe110-ch-co-exact-audit").replace(sha256_file(parent/"package/request.json"),request_sha)
    (package/"run.sbatch").write_text(script,encoding="utf8",newline="\n")
    bundle=load_json_object(parent/"package/bundle.json")
    bundle={**bundle,"remote_root":remote,"artifacts":[{"path":p.relative_to(package).as_posix(),"sha256":sha256_file(p)} for p in sorted(package.rglob('*')) if p.is_file()]}
    write_json_exclusive(package/"bundle.json",bundle)
    write_json_exclusive(root/"preparation_receipt.json",{"request_sha256":request_sha,"geometry_passed":True,
        "source_files":source_file_manifest([returned/"collection_receipt.json",contract,Path(__file__),prepare.ROOT/"scripts/mlip_same_structure_benchmark.py"])})
    transport.OUT,transport.REMOTE=root,remote
    transport.main()


if __name__=="__main__":
    main()
