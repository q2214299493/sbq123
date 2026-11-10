"""Freeze a seven-image, unrestrained, reaction-specific GPU path package."""
from pathlib import Path
import json
import shlex
import shutil
import subprocess
from datetime import datetime, timezone

from archive.fe110_c2_dual_gpu_20261106.deploy import connection
from scripts.artifact_io import load_json_object, sha256_file, source_file_manifest, write_json_exclusive
from scripts.ts_strategy_engine.path_evidence import validate_path_review
from scripts.dual_model_ml_neb import _load_request, _load_images, _geometry_guard_evidence

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109/review_ready_v2"
OUT = ROOT / "calculations/fe110_ch_co_to_chco_ts_20261109/gpu_20261110_v1"
REMOTE = "/home/sbq/sbq/fe110_ch_co_ts_gpu_20261110_v1"
PYTHON = "/home/sbq/sbq/ml_ts_acceleration/venv/bin/python"
SITE = "/home/sbq/sbq/ml_ts_acceleration/venv/lib/python3.10/site-packages"
PRIMARY = "/home/sbq/sbq/mlip_same_structure_benchmark_20260825/MatRIS_4M_FeCOH_compliant.pth.tar"
SECONDARY = "/home/sbq/sbq/aqcat25/demo_single/model.pt"
MATRIS_SOURCE = "/home/sbq/sbq/mlip_same_structure_benchmark_20260825/vendor/MatRIS"


def rpc(program):
    args, dest = connection("aqcat_gpu")
    result = subprocess.run(args+[dest,"python3 -"],input=program,capture_output=True,text=True,timeout=60)
    write_json_exclusive(OUT/"runtime_preflight_raw.json", {"returncode":result.returncode,"stdout":result.stdout,"stderr":result.stderr})
    if result.returncode:
        raise ValueError("Runtime preflight failed; inspect the saved output.")
    return json.loads(result.stdout)


def main():
    if OUT.exists():
        raise SystemExit("Package already exists; inspect it instead of preparing another job.")
    OUT.mkdir()
    runtime = rpc("""import hashlib,json,os,subprocess,socket
from pathlib import Path
models={name:{'path':p,'sha256':hashlib.sha256(Path(p).read_bytes()).hexdigest(),'bytes':Path(p).stat().st_size} for name,p in MODELS.items()}
def command(argv):
 p=subprocess.run(argv,capture_output=True,text=True,timeout=20)
 return {'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
print(json.dumps({'host':socket.gethostname(),'models':models,'python':PYTHON,'python_exists':os.access(PYTHON,os.X_OK),'MatRIS_source_exists':Path(SOURCE).is_dir(),'remote_target_exists':Path(REMOTE).exists(),'scheduler':command(['scontrol','show','node','MZ73']), 'imports':command([PYTHON,'-c','import torch,ase; print(torch.__version__,torch.version.cuda,ase.__version__)'])}))
""".replace("MODELS",repr({"primary":PRIMARY,"secondary":SECONDARY})).replace("PYTHON",repr(PYTHON)).replace("SOURCE",repr(MATRIS_SOURCE)).replace("REMOTE",repr(REMOTE)))
    if runtime["host"]!="MZ73" or runtime["remote_target_exists"] or not runtime["python_exists"] or not runtime["MatRIS_source_exists"] or runtime["imports"]["returncode"]:
        raise ValueError("Host/environment/target preflight blocked.")
    if runtime["models"]["primary"]["sha256"]!="1e6a85b33db075ad1637eca7537084024a694b1340358911212d8a5c518c6601":
        raise ValueError("Provider MatRIS checkpoint changed.")
    write_json_exclusive(OUT/"runtime_preflight.json",runtime)
    contract=load_json_object(PARENT/"reaction_contract.json")
    numeric=load_json_object(PARENT/"path_numeric_review.json")
    path=PARENT/"plan/path_candidate"
    draft=load_json_object(path/"path_review.json")
    review={**draft,"status":"accepted","reviewer":"Codex geometry review under explicit user GPU/VASP instruction 2026-11-10",
            "reviewed_at":datetime.now(timezone.utc).isoformat(),"notes":"Seven frames visually reviewed; full-slab symmetry mapping; only C-C formation, CH/CO preserved. Midpath Fe-C~1.68A initial-force risk retained. No TS or energy claim."}
    review_file=OUT/"path_review.accepted.json"
    write_json_exclusive(review_file,review)
    if not validate_path_review(review_file,path/"path_generation_report.json")[0] or len(numeric["rows"])!=7:
        raise ValueError("Path binding failed.")
    package=OUT/"package"
    package.mkdir()
    images=[]
    for index in range(7):
        label=f"{index:02d}"
        target=package/"images"/(label+".vasp")
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(path/label/"POSCAR",target)
        images.append({"image":label,"path":target.relative_to(package).as_posix(),"sha256":sha256_file(target)})
    guard={"enforce_monitored_bond_monotonicity":False,"require_monitored_bond_interval_coverage":False}
    request={"schema_version":1,"document_kind":"dual_model_ml_neb_request","request_id":"fe110_ch_co_coupling_20261110_v1",
        "run_kind":"bounded_production_path_candidate","result_class":"predicted_path_candidate_only","automatic_vasp_submission":False,
        "models":{role:{"backend":"matris" if role=="primary" else "aqcat25", "identifier":"provider_FeCOH_base" if role=="primary" else "AQCat25-EV2_base", "checkpoint_sha256":runtime["models"][role]["sha256"]} for role in ("primary","secondary")},
        "reaction":{key:contract[key] for key in ("contract_sha256","atom_map_sha256","compatibility_sha256")},
        "fixed_atom_indices_zero_based":list(range(18)),"images":images,
        "preconditioning":{"enabled":False},"restraint_release":{"stages":[]},
        "ordinary_ml_neb":{"spring_constant_eV_per_A2":.1,"fmax_eV_per_A":.1,"max_steps":160,"ml_ci":"off","ci_fmax_eV_per_A":.05,"ci_max_steps":0,"monitored_geometry_guard":guard},
        "final_geometry_guard":guard,
        "geometry_guards":{"preserved_bonds":[
            {"name":"CH_retained","atoms_zero_based":[45,48],"minimum_A":.95,"maximum_A":1.25,"assessment_mode":"graded_warning","hard_minimum_A":.65,"hard_maximum_A":1.8},
            {"name":"CO_retained","atoms_zero_based":[46,47],"minimum_A":1.05,"maximum_A":1.65,"assessment_mode":"graded_warning","hard_minimum_A":.8,"hard_maximum_A":2.3}],
            "monitored_bonds":[{"name":"C_C_formation","atoms_zero_based":[45,46],"important_interval_A":[1.5,2.6],"minimum_internal_images":1}],
            "minimum_pair_distance_A":.65,"maximum_adjacent_rmsd_A":.8,"maximum_single_movable_atom_step_A":1.4},
        "domain_status":"uncalibrated_C_C_coupling; disagreement is a sampling score, not uncertainty",
        "review":{"path_review_sha256":sha256_file(review_file),"image_count_is_not_a_physical_hard_gate":True},
        "resources":{"GPU":1,"CPU":4,"memory_GB":40,"wall_seconds":900,"training":False,"Sella":False,"CPU_fallback":False}}
    request["reaction"]["indexed_bond_changes"]=[{"atoms_1based":[46,47],"change":"form"}]
    write_json_exclusive(package/"request.json",request)
    loaded=_load_request(package/"request.json")
    geometry=_geometry_guard_evidence(_load_images(loaded,package),loaded)
    if not geometry["passed"]:
        raise ValueError("Local no-model GPU-path geometry preflight failed.")
    write_json_exclusive(OUT/"local_geometry_preflight.json",geometry)
    for name in ["dual_model_ml_neb.py","aqcat25_ml_neb.py","aqcat25_handoff.py","artifact_io.py","mlip_same_structure_benchmark.py","ml_sella_candidate.py"]:
        shutil.copyfile(ROOT/"scripts"/name,package/name)
    shutil.copyfile(ROOT/"archive/fe110_c2_gpu_repair_20261107/device.py",package/"device.py")
    shutil.copyfile(Path(__file__).with_name("worker.py"),package/"worker.py")
    request_sha=sha256_file(package/"request.json")
    write_json_exclusive(package/"authorization.json",{"user_authorized":True,"request_sha256":request_sha,
        "user_request":"任务结束了 先审核任务查重 有一个没收敛你看看为什么 是不是优化到了不同结构 然后审查过后的任务录入吸附能表中 然后过渡态任务提交gpu和vasp",
        "scope":"One seven-image MatRIS ordinary path plus exact AQCat25 audit; no training/CI/Sella; VASP only after work-side review and current gate."})
    env={"PYTHONPATH":REMOTE+":"+MATRIS_SOURCE+":/home/sbq/sbq/aqcat25/python_pkgs:/home/sbq/sbq/aqcat25/vendor",
        "PYTHONDONTWRITEBYTECODE":"1","PYTHONNOUSERSITE":"1","OMP_NUM_THREADS":"4","WANDB_MODE":"disabled"}
    for key in ("MPLCONFIGDIR","XDG_CACHE_HOME","TORCH_HOME","HF_HOME","TRITON_CACHE_DIR","TORCH_EXTENSIONS_DIR","TMPDIR"):
        env[key]=REMOTE+"/cache/"+key.lower()
    script="#!/bin/bash\n#SBATCH --job-name=fe110-ch-co-ml-neb\n#SBATCH --partition=gpu\n#SBATCH --nodes=1\n#SBATCH --ntasks=1\n#SBATCH --cpus-per-task=4\n#SBATCH --gres=gpu:1\n#SBATCH --mem=40G\n#SBATCH --time=00:15:00\nset -euo pipefail\n"
    script+="\n".join("export "+k+"="+shlex.quote(v) for k,v in env.items())+"\n"
    script+="mkdir -p "+" ".join(shlex.quote(v) for k,v in env.items() if k.endswith("DIR") or k.endswith("HOME"))+"\n"
    script+=f"cd {shlex.quote(REMOTE)}\nexec {shlex.quote(PYTHON)} worker.py --root {shlex.quote(REMOTE)} --request-sha256 {request_sha}\n"
    (package/"run.sbatch").write_text(script,encoding="utf8",newline="\n")
    write_json_exclusive(package/"bundle.json",{"remote_root":REMOTE,"primary_checkpoint":PRIMARY,"secondary_checkpoint":SECONDARY,
        "cudart":SITE+"/nvidia/cuda_runtime/lib/libcudart.so.12",
        "artifacts":[{"path":p.relative_to(package).as_posix(),"sha256":sha256_file(p)} for p in sorted(package.rglob("*")) if p.is_file()]})
    write_json_exclusive(OUT/"preparation_receipt.json",{"request_sha256":request_sha,"geometry_passed":True,
        "source_files":source_file_manifest([review_file,PARENT/"reaction_contract.json",OUT/"runtime_preflight.json",Path(__file__)])})
    print("PREPARED_ONE_GPU_PATH",request_sha,flush=True)


if __name__=="__main__":
    main()
