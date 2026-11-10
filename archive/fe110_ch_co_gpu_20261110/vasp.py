"""Prepare the first VASP path from the returned, audited GPU path."""
from datetime import datetime,timezone
from pathlib import Path
import argparse
import shutil
import subprocess
import json

import numpy as np
import yaml
from ase.io import read

from scripts.artifact_io import load_json_object,sha256_file,source_file_manifest,write_json_exclusive
from scripts.adsorption.build_fe110_adsorption import read_poscar
from scripts.neb_agent.generate_path import generate_path
from scripts.neb_agent.diagnose_path_geometry import diagnose
from scripts.neb_agent.analyze_neb_outputs import analyze
from scripts.neb_agent.submission import preflight,submit
from scripts.registry_connection import open_registry
from scripts.ts_strategy_engine.contract import load_contract
from scripts.ts_strategy_engine.fingerprint import build_fingerprint
from scripts.ts_strategy_engine.path_evidence import validate_path_binding,validate_path_review
from scripts.ts_strategy_engine.execution_gate import decide_execution,require_action
from scripts.ts_strategy_engine.execution_evidence import execution_evidence_sha256,workdir_identity
from scripts.vasp_inputs import build_fe110_neb
from .prepare import ROOT,PARENT

AUDIT=PARENT.parent/"gpu_fixed_path_audit_20261110_v2/return_12406"
OUT=PARENT.parent/"vasp_ordinary_neb_20261110_v1"
REMOTE="~/sbq/Fe110/ts/ch_co_to_chco_20261110/vasp_ordinary_neb_20261110_v1"
AUTH=ROOT/"docs/reviews/fe110_c2_completion_20261110_user_authorization.md"
THRESHOLDS=ROOT/"configs/neb_agent/default_thresholds.yaml"
HOST="sunboquan-codex"


def prepare():
    if OUT.exists():raise SystemExit("Keep the existing initial VASP package.")
    returned=load_json_object(AUDIT/"collection_receipt.json")
    for r in returned["files"]:
        if sha256_file(AUDIT/r["path"])!=r["sha256"]:raise ValueError("Returned producer source changed.")
    manifest=load_json_object(AUDIT/"output/dual_model_gpu_ml_neb_path_manifest.candidate.json")
    if not manifest["geometry_guards"]["passed"] or not manifest["optimizer"]["final_converged"]:
        raise ValueError("GPU primary source geometry/convergence requires review.")
    if load_json_object(AUDIT/"worker_exit.json")["GPU_models_loaded"]!=["matris","aqcat25"]:
        raise ValueError("Both exact-path GPU model devices were not proved.")
    for role in ("matris","aqcat25"):
        device=load_json_object(AUDIT/"admission"/(role+"_model_device.json"))
        if device["model_devices"]!=["cuda:0"]:raise ValueError("Not actual CUDA execution.")
    OUT.mkdir()
    sources=[AUDIT/"output"/r["structure_path"] for r in manifest["images"]]
    for source,row in zip(sources,manifest["images"],strict=True):
        if sha256_file(source)!=row["structure_sha256"]:raise ValueError("GPU image hash changed.")
    generated=generate_path(sources[3],sources[4],OUT/"local_idpp_03_04",1,"idpp",None,[])
    if generated["status"]=="STOP":raise ValueError("Local geometric insertion failed.")
    selected=sources[:4]+[OUT/"local_idpp_03_04/01/POSCAR"]+sources[4:]
    for i,source in enumerate(selected):
        folder=OUT/f"{i:02d}"
        folder.mkdir()
        shutil.copyfile(source,folder/"POSCAR")
    contract=load_contract(PARENT/"reaction_contract.json")
    write_json_exclusive(OUT/"reaction_contract.normalized.json",contract)
    fingerprint=build_fingerprint(contract)
    write_json_exclusive(OUT/"path_generation_report.json",{
        "status":"READY_FOR_REVIEW","method_used":"reviewed_full_GPU_path_plus_one_local_full_atom_IDPP_image",
        "interior_images":6,"image_directories":[f"{i:02d}" for i in range(8)],
        "contract_sha256":contract["contract_sha256"],"atom_map_sha256":contract["atom_map_sha256"],
        "compatibility_sha256":contract["compatibility_sha256"],"fingerprint_id":fingerprint["fingerprint_id"],
        "GPU_path_manifest":{"path":str(AUDIT/"output/dual_model_gpu_ml_neb_path_manifest.candidate.json"),"sha256":sha256_file(AUDIT/"output/dual_model_gpu_ml_neb_path_manifest.candidate.json")},
        "new_image_04":"One all-atom IDPP point in GPU03-04; no model energy/force assigned to interpolated point.",
        "source_files":source_file_manifest(selected)})
    settings=build_fe110_neb(OUT,images=6,cores=96)
    write_json_exclusive(OUT/"input_generation_manifest.json",settings)
    geometry=diagnose(OUT,[str(i) for i in contract["reaction_atoms"]],[],THRESHOLDS,reaction_pairs=contract["formed_bonds"],expected_interior=6)
    if geometry["status"]=="STOP":raise ValueError("Initial VASP geometry blocked.")
    finish()


def finish():
    settings=load_json_object(OUT/"input_generation_manifest.json")
    custodian=Path("C:/Users/86177/.codex/skills/fe-vasp-incar-custodian/scripts/incar_custodian.py")
    custodian_result=OUT/"incar_custodian_check_v2.json"
    if custodian_result.exists():
        result_data=load_json_object(custodian_result)
    else:
        result=subprocess.run(["C:/Anaconda/python.exe","-X","utf8",str(custodian),"--mode","validate","--workdir",str(OUT),
            "--incar",str(OUT/"INCAR"),"--poscar",str(OUT/"00/POSCAR"),"--calculation-type","pre_NEB","--surface-family","metal_fe","--material","Fe110","--read-only"],
            capture_output=True,text=True,timeout=60)
        result_data={"returncode":result.returncode,"stdout":result.stdout,"stderr":result.stderr}
        write_json_exclusive(custodian_result,result_data)
    if result_data["returncode"]:raise ValueError("Custodian command failed; see preserved stderr.")
    check=json.loads(result_data["stdout"])
    if check["blockers"]:raise ValueError("Custodian validation blocked.")
    perl="C:/Program Files/Git/usr/bin/perl.exe"
    tool=ROOT/"archive/vtst_review_job9745217/dist.pl"
    distances=[]
    for i in range(7):
        p=subprocess.run([perl,tool.as_posix(),(OUT/f"{i:02d}/POSCAR").as_posix(),(OUT/f"{i+1:02d}/POSCAR").as_posix()],capture_output=True,text=True,check=True)
        distances.append({"left":f"{i:02d}","right":f"{i+1:02d}","distance_A":float(p.stdout.strip())})
    write_json_exclusive(OUT/"dist.json",{"tool_sha256":sha256_file(tool),"pairs":distances})
    movie=ROOT/"archive/vtst_review_job9745217/nebmovie.pl"
    posix="/c/"+movie.as_posix().split(":/",1)[1]
    subprocess.run(["C:/Program Files/Git/bin/bash.exe","--noprofile","--norc","-c","export PATH=/usr/bin:/bin:$PATH; /usr/bin/perl "+posix+" 0"],cwd=OUT,check=True)
    rows=[]
    poses=[]
    for i in range(8):
        atoms=read(OUT/f"{i:02d}/POSCAR",format="vasp")
        rows.append({"image":f"{i:02d}","C_C_A":float(atoms.get_distance(45,46,mic=True)),"C_H_A":float(atoms.get_distance(45,48,mic=True)),"C_O_A":float(atoms.get_distance(46,47,mic=True))})
        poses.append(read_poscar(OUT/f"{i:02d}/POSCAR"))
    write_json_exclusive(OUT/"structure_review_table.json",{"rows":rows,"DFT_outputs_exist":False})
    render(poses,rows)
    print("INITIAL_VASP_PATH_READY",settings["cores"],settings["incar"],rows,flush=True)


def render(poses,rows):
    import matplotlib.pyplot as plt
    plt.switch_backend("Agg")
    fig,axes=plt.subplots(2,8,figsize=(19,5.8))
    colors=["#202c39","#202c39","#dc2626","#38bdf8"]
    for col,(pose,row) in enumerate(zip(poses,rows,strict=True)):
        cart=pose.frac@pose.cell
        surface=np.argsort(cart[:45,2])[-9:]
        for r,dims in enumerate(((0,1),(0,2))):
            ax=axes[r,col]
            ax.scatter(cart[surface,dims[0]],cart[surface,dims[1]],s=75,c="#a1a1aa")
            for atom,color in zip(range(45,49),colors,strict=True):
                ax.scatter(cart[atom,dims[0]],cart[atom,dims[1]],s=55,c=color,zorder=3)
            for pair in ([45,48],[46,47],[45,46]):ax.plot(cart[pair,dims[0]],cart[pair,dims[1]],color="#64748b",linewidth=1)
            ax.set_xlim(4.2,9.5)
            ax.set_ylim((.8,4.8) if r==0 else (14,19))
            ax.set_aspect("equal")
        axes[0,col].set_title(row["image"]+" CC "+f"{row['C_C_A']:.3f}",fontsize=9)
    fig.suptitle("First VASP ordinary-NEB seed: reviewed MatRIS path + local image04 insertion; not a TS/barrier")
    fig.tight_layout(rect=(0,0,1,.94))
    fig.savefig(OUT/"initial_path_review.png",dpi=150)
    plt.close(fig)


def gate_submit():
    if (OUT/"submission_attempt.json").exists() or (OUT/"submission_record.json").exists():
        raise ValueError("Existing reservation/receipt; never repeat this submission.")
    contract=load_contract(OUT/"reaction_contract.normalized.json")
    review={"status":"accepted","reviewer":"Codex work-side numeric and visual review under explicit user submission authority",
        "reviewed_at":datetime.now(timezone.utc).isoformat(),"dist_file":str(OUT/"dist.json"),"dist_sha256":sha256_file(OUT/"dist.json"),
        "nebmovie_file":str(OUT/"movie"),"nebmovie_sha256":sha256_file(OUT/"movie"),
        "path_generation_sha256":sha256_file(OUT/"path_generation_report.json"),
        "notes":"Eight frames visually reviewed; local image04 fills 2.314-1.459A CC gap at1.886A. CH/CO retained; endpoints fixed to accepted DFT states via reviewed symmetry mapping. Initial ordinary VASP only,not CI/Dimer/TS."}
    if not (OUT/"path_review.json").exists():
        write_json_exclusive(OUT/"path_review.json",review)
    if not validate_path_review(OUT/"path_review.json",OUT/"path_generation_report.json")[0]:raise ValueError("Path review binding invalid.")
    geometry=load_json_object(OUT/"path_geometry_diagnosis.json")
    if geometry["status"]!="PASS":raise ValueError("Geometry not passed.")
    analysis=load_json_object(OUT/"neb_analysis.json") if (OUT/"neb_analysis.json").exists() else analyze(OUT,THRESHOLDS,contract["reaction_atoms"])
    binding=validate_path_binding(OUT,contract)
    analysis.update(path_binding=binding,path_binding_valid=binding["valid"],path_reviewed=True,
                    contract_sha256=contract["contract_sha256"],atom_map_sha256=contract["atom_map_sha256"],compatibility_sha256=contract["compatibility_sha256"])
    if analysis["status"]!="NO_OUTPUT" or not binding["valid"]:raise ValueError("Initial-path analysis/binding differs.")
    if not (OUT/"neb_analysis.bound.json").exists():
        write_json_exclusive(OUT/"neb_analysis.bound.json",analysis)
    elif load_json_object(OUT/"neb_analysis.bound.json")!=analysis:
        raise ValueError("Bound initial analysis changed.")
    report=preflight(OUT,"ordinary_neb",write_report=False)
    ready_preflight=OUT/"submission_preflight.ready.json"
    if not ready_preflight.exists():
        write_json_exclusive(ready_preflight,report)
    elif load_json_object(ready_preflight)!=report:
        raise ValueError("Ready preflight changed; prepare a fresh binding.")
    if not report["passed"]:raise ValueError("Input preflight: "+repr(report["errors"]))
    potcar_source="~/sbq/Fe110/adsorption/fe110_five_c2_20261006/03_cfg0_direct_vasp/POTCAR"
    potcar_sha=contract["compatibility"]["potcar_bundle_sha256"]
    program=r'''import os,hashlib,json,subprocess
def command(args):
 p=subprocess.run(args,capture_output=True,text=True,timeout=20)
 return {'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
print(json.dumps({'user':command(['whoami']),'account':command(['busers','-w']),'active_jobs':command(['bjobs','-w']),
 'remote_target_exists':os.path.lexists(os.path.expanduser(TARGET)),
 'remote_reservation_exists':os.path.lexists(os.path.expanduser(TARGET+'.submission-reservation')),
 'VASP_exists':os.access(os.path.expanduser('~/soft/vasp541vtst/bin/vasp_std'),os.X_OK),
 'Intel_environment_exists':os.path.isfile('/home_gkx/env/intel/intel2016.sh'),
 'POTCAR_sha256':hashlib.sha256(open(os.path.expanduser(POTCAR),'rb').read()).hexdigest()}))
'''.replace("TARGET",repr(REMOTE)).replace("POTCAR)",repr(potcar_source)+")")
    # Keep the data variable separate from the output JSON's POTCAR key.
    program=program.replace("expanduser(POTCAR)","expanduser("+repr(potcar_source)+")")
    result=subprocess.run(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=15",HOST,"python3 -"],input=program,capture_output=True,text=True,timeout=45)
    write_json_exclusive(OUT/"remote_precheck_raw_v2.json",{"returncode":result.returncode,"stdout":result.stdout,"stderr":result.stderr})
    if result.returncode:raise ValueError("Remote preflight failed.")
    remote=json.loads(result.stdout)
    write_json_exclusive(OUT/"remote_precheck_v2.json",remote)
    if (remote["user"]["stdout"].strip()!="nsgkn_chengdj3" or remote["remote_target_exists"] or remote["remote_reservation_exists"]
          or not remote["VASP_exists"] or not remote["Intel_environment_exists"] or remote["POTCAR_sha256"]!=potcar_sha):
        raise ValueError("Remote identity/target/runtime/POTCAR failed.")
    thresholds=yaml.safe_load(THRESHOLDS.read_text(encoding="utf8"))
    bindings={key:{"path":str(path),"sha256":sha256_file(path)} for key,path in [
        ("geometry",OUT/"path_geometry_diagnosis.json"),("analysis",OUT/"neb_analysis.bound.json"),
        ("thresholds",THRESHOLDS),("preflight",ready_preflight)]}
    kwargs={"climb":False,"path_reviewed":True,"preflight":report,"source_bindings":bindings}
    evidence=decide_execution(geometry,analysis,thresholds,**kwargs)["EVIDENCE"]
    authorization={"schema_version":1,"document_kind":"user_execution_authorization","action":"SUBMIT_VASP","calculation_kind":"ordinary_neb",
        "authorized_at":datetime.now(timezone.utc).isoformat(),"source":{"path":str(AUTH),"sha256":sha256_file(AUTH)},
        "target":{"server_alias":HOST,"remote_dir":REMOTE},"workdir_identity":workdir_identity(OUT),
        "bundle_sha256":report["bundle_sha256"],"evidence_sha256":execution_evidence_sha256(evidence),
        "potcar":{"source":potcar_source,"sha256":potcar_sha,"spec_sha256":report["files"]["POTCAR.spec"]}}
    write_json_exclusive(OUT/"user_execution_authorization.v2.json",authorization)
    bindings["authorization"]={"path":str(OUT/"user_execution_authorization.v2.json"),"sha256":sha256_file(OUT/"user_execution_authorization.v2.json")}
    gate=decide_execution(geometry,analysis,thresholds,authorization=authorization,**kwargs)
    write_json_exclusive(OUT/"submission_decision.v2.json",gate)
    require_action(OUT/"submission_decision.v2.json","SUBMIT_VASP",gate["state_sha256"])
    receipt=submit(OUT,OUT/"submission_decision.v2.json",HOST,REMOTE,potcar_source,potcar_sha,"SUBMIT_VASP")
    print("ORDINARY_NEB_SUBMITTED",receipt["job_id"],receipt["status"],flush=True)


def tool_views():
    dist=load_json_object(OUT/"dist.json")
    if (OUT/"dist.dat").exists() or (OUT/"movie.xyz").exists():
        raise ValueError("Tool compatibility exports exist; do not overwrite.")
    (OUT/"dist.dat").write_text("# left right VTST_distance_A\n"+"".join(r["left"]+" "+r["right"]+" "+format(r["distance_A"],".17g")+"\n" for r in dist["pairs"]),encoding="ascii")
    frames=[OUT/f"{i:02d}/POSCAR.xyz" for i in range(8)]
    with (OUT/"movie.xyz").open("xb") as target:
        for source in frames:target.write(source.read_bytes())
    movie_frames=read(OUT/"movie.xyz",index=":",format="xyz")
    if len(movie_frames)!=8 or any(len(frame)!=49 for frame in movie_frames):
        raise ValueError("VTST XYZ concatenation failed.")
    write_json_exclusive(OUT/"tool_views_receipt.json",{"method":"Exact concatenation of eight native VTST per-image POSCAR.xyz; original nebmovie 'movie' retained; dist table from seven actual dist.pl outputs.",
        "source_files":source_file_manifest([OUT/"dist.json",OUT/"movie",*frames]),"movie_xyz_sha256":sha256_file(OUT/"movie.xyz"),"dist_dat_sha256":sha256_file(OUT/"dist.dat")})


def submit_reviewed():
    """Publish the current canonical preflight, then submit the existing binding once."""
    if (OUT/"submission_attempt.json").exists() or (OUT/"submission_record.json").exists():
        raise ValueError("Existing reservation/receipt; reconcile, never repeat submission.")
    ready=load_json_object(OUT/"submission_preflight.ready.json")
    current=preflight(OUT,"ordinary_neb",write_report=False)
    if not current["passed"] or current!=ready:
        raise ValueError("Reviewed preflight changed; do not submit.")
    decision=OUT/"submission_decision.v2.json"
    gate=load_json_object(decision)
    require_action(decision,"SUBMIT_VASP",gate["state_sha256"])
    original=OUT/"submission_preflight.json"
    backup=OUT/"submission_preflight.initial_failed.json"
    if load_json_object(original)!=ready:
        if backup.exists():
            raise ValueError("Prior preflight backup exists; inspect before any further write.")
        shutil.copyfile(original,backup)
        published=preflight(OUT,"ordinary_neb",write_report=True)
        if published!=ready or load_json_object(original)!=ready:
            raise ValueError("Canonical preflight differs from the reviewed binding.")
    auth=load_json_object(OUT/"user_execution_authorization.v2.json")
    receipt=submit(OUT,decision,HOST,REMOTE,auth["potcar"]["source"],auth["potcar"]["sha256"],"SUBMIT_VASP")
    print("ORDINARY_NEB_SUBMITTED",receipt["job_id"],receipt["status"],flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument("phase",choices=["prepare","finish","gate-submit","tool-views","submit-reviewed"])
    args=parser.parse_args()
    {"prepare":prepare,"finish":finish,"gate-submit":gate_submit,"tool-views":tool_views,"submit-reviewed":submit_reviewed}[args.phase]()
