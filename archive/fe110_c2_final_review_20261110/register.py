"""Prepare one reviewed append-only completion batch; no implicit apply."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json

from archive.fe110_c2_supplement_vasp_20261107.dft import SUBMISSION
from scripts.adsorption.prepare_completion_registration import compatibility, result_evidence, check_decision
from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.registry_connection import open_registry
from scripts.scheduler_evidence import _parse_lsf_bjobs
from .collect import OUT, ROOT

DB=ROOT/"data/project_registry.sqlite3"
AUTH=ROOT/"docs/reviews/fe110_c2_completion_20261110_user_authorization.md"
REVIEWER="Codex adsorption owner review under explicit user authority 2026-11-10"
ACCEPT={"05_S2","07_S1","12_S1","13_S1","18_S2"}
EXCEPTION={"05_S2":"9963757","07_S1":"9963759","12_S1":"9963761"}
IDENTITY={"05":"[C]-[C]-OH","06":"[C]-O-[CH]","07":"[CH2]-[C]-[O]","11":"[C]-CH3",
          "12":"CH3-[C]-[O]","13":"[CH2]-[C]-OH","14":"[C]-O-CH3","18":"[CH]-O-CH3"}


def formula(symbols):
    counts=Counter(symbols)
    return "".join(s+(str(counts[s]) if counts[s]>1 else "") for s in ("C","H","O") if counts[s])


def main():
    target=OUT/"registry_batch.json"
    if target.exists():
        raise SystemExit("Batch exists; inspect its saved plan/receipt rather than regenerating.")
    analysis=load_json_object(OUT/"completion_geometry_review.json")
    duplicates=load_json_object(OUT/"duplicate_review_v2.json")
    geometry={r["name"]:r for r in load_json_object(OUT/"force_geometry_final_review.json")["records"]}
    mapping={r["name"]:r for r in duplicates["decisions"]}
    manifest=load_json_object(OUT/"collection_manifest.json")
    ready={r["name"]:r for r in load_json_object(SUBMISSION/"ready_for_submission.json")["jobs"]}
    if "允许这三个按完整、哈希核验的 VASP 证据" not in AUTH.read_text(encoding="utf8"):
        raise ValueError("Exact three-case user exception missing.")
    now=datetime.now(timezone.utc).isoformat()
    rows={k:[] for k in ("files","results","reviews","calculation_compatibility","job_status_history")}
    changes,provenance,decisions=[],{},[]
    reviewdir=OUT/"scientific_reviews"
    reviewdir.mkdir()
    slab=ROOT/"calculations/true_fe110_clean_20260629/results/job_9557161/CONTCAR"
    with open_registry(DB) as db:
        db.execute("PRAGMA query_only=ON")
        event=db.execute("SELECT coalesce(max(status_event_id),0) FROM job_status_history").fetchone()[0]
        for record in analysis["records"]:
            name=record["name"]
            cid="fe110_c2_supplement_20261107_"+name+"_vasp_v1"
            calc=db.execute("SELECT workflow_status FROM calculations WHERE calculation_id=?",(cid,)).fetchone()
            job=db.execute("SELECT * FROM jobs WHERE calculation_id=? AND scheduler_job_id=?",(cid,record["job_id"])).fetchone()
            if calc is None or job is None or db.execute("SELECT 1 FROM results WHERE calculation_id=?",(cid,)).fetchone():
                raise ValueError("Unexpected prior registration; reconcile "+name)
            prefix=cid+"_completion_20261110"
            duplicate=mapping[name].get("duplicate_of")
            accepted=name in ACCEPT
            verdict="accept" if accepted else "duplicate" if duplicate else "needs_review"
            try:queue=_parse_lsf_bjobs(manifest["bjobs"]["stdout"],record["job_id"])
            except ValueError:queue="UNKNOWN"
            if accepted:
                if mapping[name]["decision"]!="unique_candidate" or record["blockers"] or not geometry[name]["coordinate_force_correspondence_passed"]:
                    raise ValueError("Accepted record fails owner evidence: "+name)
                if name in EXCEPTION:
                    if record["job_id"]!=EXCEPTION[name] or queue!="UNKNOWN":
                        raise ValueError("Exception scope changed.")
                else:
                    check_decision({"eligible_for_review":True,"duplicate_of":None},{"decision":"accept"},{"status":queue})
            elif duplicate:
                check_decision({"eligible_for_review":True,"duplicate_of":duplicate},{"decision":"duplicate"})
            reason=("Complete normally terminated/electronically and ionically converged VASP, fmax<=0.02, force-position correspondence, compatible branch, intact chemistry and surface-aware uniqueness reviewed.") if accepted else ("Surface-symmetry, chemically mapped RMSD and compatible energy match accepted "+duplicate+"; retain source without another independent accepted row.") if duplicate else ("Previously user-stopped; C-O cleavage; no accepted original or product minimum.") if name=="06_S2" else "NSW300 ended with fmax0.07719976eV/A; C45-H48 dehydrogenation to surface H; neither intact adsorption nor converged product accepted. No retry."
            if name in EXCEPTION:
                reason+=" Exact user exception: historical scheduler unavailable after bjobs/bhist/bacct checks; queue remains UNKNOWN."
            comp=compatibility({"formula":formula(record["symbols"])},{"remote":{"files":{"POTCAR":{"sha256":ready[name]["potcar_sha256"]}}}},
                               {"slab":{"path":str(slab),"sha256":sha256_file(slab)}})
            old=db.execute("SELECT compatibility_json FROM calculation_compatibility WHERE calculation_id=?",(cid,)).fetchone()
            if old is None:
                rows["calculation_compatibility"].append({"calculation_id":cid,"compatibility_fingerprint":sha256_json(comp),
                    "compatibility_json":json.dumps(comp,sort_keys=True,separators=(",",":")),"reviewer":REVIEWER,"reviewed_at":now})
            elif json.loads(old[0])!=comp:
                raise ValueError("Do not replace immutable compatibility.")
            sources=[r for r in manifest["files"] if r["relative_path"].split('/')[0]==name]
            for source in sources:
                local=OUT/"sources"/source["relative_path"]
                if sha256_file(local)!=source["sha256"]:
                    raise ValueError("Collected source changed.")
                rows["files"].append({"file_id":prefix+"_"+local.name,"calculation_id":cid,"job_record_id":job["job_record_id"],
                    "role":"completion_source","filename":local.name,"local_path":str(local),
                    "remote_path":manifest["root"]+"/"+source["relative_path"],"storage_mode":"local_and_remote",
                    "byte_size":source["bytes"],"sha256":source["sha256"],"existence_status":"confirmed"})
            review=reviewdir/(name+".json")
            decision={"name":name,"calculation_id":cid,"decision":verdict,"duplicate_of":duplicate,"queue_status":queue,
                      "formula":formula(record["symbols"]),"target_graph":IDENTITY[name[:2]],"reason":reason}
            decisions.append(decision)
            write_json_exclusive(review,{"decision":decision,"evidence":record,"geometry":geometry[name],
                "reviewer":REVIEWER,"reviewed_at":now,"visual_review":"unique_final_structures.png and ineligible_final_structures.png; preserved graphs/contacts and failure reviewed",
                "duplicate_analysis_sha256":sha256_file(OUT/"duplicate_review_v2.json"),"authorization_sha256":sha256_file(AUTH)})
            rows["files"].append({"file_id":prefix+"_review_source","calculation_id":cid,"role":"scientific_review","filename":review.name,
                "local_path":str(review),"storage_mode":"local_only","byte_size":review.stat().st_size,"sha256":sha256_file(review),"existence_status":"confirmed"})
            rows["reviews"].append({"review_id":prefix+"_review","calculation_id":cid,"review_type":"adsorption_completion_geometry_chemistry_and_duplicate",
                "decision":verdict,"reviewer":REVIEWER,"reviewed_at":now,"evidence":str(review)+"#sha256="+sha256_file(review),"reason":reason})
            if name!="06_S2":
                event+=1
                rows["job_status_history"].append({"status_event_id":event,"job_record_id":job["job_record_id"],"scheduler_status":queue,
                    "scientific_status":"reviewed_"+verdict if name!="18_S1" else "force_not_converged_changed_chemistry",
                    "checked_at":now,"source_command":"ssh sunboquan-codex bjobs -a -w <exact ten submitted jobs>; bhist -l; bacct -l",
                    "source_text":manifest["bjobs"]["stdout"]+manifest["bjobs"]["stderr"],"reviewer":REVIEWER,"notes":reason})
            current=calc[0]
            targets=["accepted"] if accepted else ["needs_review","duplicate"] if duplicate else ["needs_review"] if name!="06_S2" else []
            for i,status in enumerate(targets):
                changes.append({"status_change_id":prefix+"_status"+str(i),"calculation_id":cid,"expected_workflow_status":current,
                    "new_workflow_status":status,"changed_at":now,"reviewer":REVIEWER,"reason":reason})
                current=status
            if name=="06_S2":
                continue
            validation={"owner":"vasp_relaxation","directory":record["directory"],
                "source_files":{n:sha256_file(Path(record["directory"])/n) for n in ("INCAR","POSCAR","CONTCAR","OUTCAR","OSZICAR")},
                "completion_review_sha256":sha256_file(review)}
            identity={"formula":decision["formula"],"target_graph":decision["target_graph"],"intact":record["chemistry_same"],
                      "duplicate_of":duplicate,"scheduler_status":queue}
            for kind,value,text,unit in [("final_toten",record["TOTEN_eV"],None,"eV"),
                 ("final_max_movable_force",record["fmax_movable_eV_A"],None,"eV/angstrom"),
                 ("final_state_identity",None,json.dumps(identity,ensure_ascii=False),None)]:
                result={"result_id":prefix+"_"+kind,"calculation_id":cid,"result_name":kind,"numeric_value":value,"text_value":text,
                    "unit":unit,"source_file_id":prefix+("_CONTCAR" if kind=="final_state_identity" else "_OUTCAR"),
                    "reference_convention":comp["final_energy_convention"] if kind=="final_toten" else "reviewed_final_structure_or_force",
                    "source_locator":"last complete energy/force block; coordinate correspondence reviewed",
                    "extraction_method":"owning VASP parsers and explicit scientific/source review",
                    "validation_status":"accepted_compatible_final_energy" if accepted and kind=="final_toten" else "reviewed",
                    "created_at":now,"notes":reason+" No E0/Eads inferred."}
                rows["results"].append(result)
                provenance[result["result_id"]]=result_evidence(result,validation,comp,review,REVIEWER,now)
    write_json_exclusive(OUT/"scientific_decisions.json",{"reviewer":REVIEWER,"reviewed_at":now,"decisions":decisions,
        "analysis_sha256":sha256_file(OUT/"completion_geometry_review.json"),"authorization_sha256":sha256_file(AUTH)})
    write_json_exclusive(target,{"schema_version":1,"document_kind":"calculation_registry_batch","batch_id":"fe110_c2_supplement_completion_20261110_v1",
        "created_at":now,"reviewer":REVIEWER,"reason":"Reviewed ten sources;five accepted unique,three duplicates,two ineligible;explicit three-case UNKNOWN exception;no new adsorption jobs.",
        "rows":rows,"workflow_status_changes":changes,"result_provenance":provenance})
    print("PREPARED",{k:len(v) for k,v in rows.items()},"accepted_unique",len(ACCEPT),flush=True)


if __name__=="__main__":
    main()
