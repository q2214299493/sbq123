"""Recover two existing C3 jobs through known relative paths; remote read-only."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

from scripts.artifact_io import sha256_file, write_json


CASES = [
    {"job_id": "9629858", "name": "01_single_C_top",
     "directory": "sbq/Fe110/adsorption/care_c3h2o_rebuild_pair_20260717/01_single_C_top",
     "input": "calculations/fe110_care8_isomers_20260716/rebuilt/08_C3H2O_XXNRTDXE_cfg0_intact_vertical"},
    {"job_id": "9629859", "name": "02_h_lb_h_dual_end",
     "directory": "sbq/Fe110/adsorption/care_c3h2o_rebuild_pair_20260717/02_h_lb_h_dual_end",
     "input": "calculations/fe110_care8_isomers_20260716/rebuilt/08_C3H2O_XXNRTDXE_cfg0_h_lb_h_dual_end"},
]
FILES = ("INCAR", "POSCAR", "CONTCAR", "OUTCAR", "OSZICAR", "KPOINTS")
OUTPUT = Path("calculations/fe110_c3_existing_recovery_20261023/collection_v1")
SSH = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=15"]


def collect(case: dict) -> dict:
    root = OUTPUT / case["job_id"]
    root.mkdir(parents=True, exist_ok=True)
    receipt = root / "collection.json"
    if receipt.exists():
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        if saved["case"] != case or any(sha256_file(root / n) != saved["remote"][n]["sha256"] for n in FILES):
            raise ValueError("existing collection binding changed")
        return saved
    script = """
import json,os,subprocess,sys
root=ROOT
result={}
for name in NAMES:
 p=os.path.join(root,name)
 print('READING '+name,file=sys.stderr,flush=True)
 digest=subprocess.check_output(['sha256sum',p]).decode('ascii').split()[0]
 result[name]={'sha256':digest,'bytes':os.stat(p).st_size}
print(json.dumps(result))
""".replace("ROOT", repr(case["directory"])).replace("NAMES", repr(FILES + ("POTCAR",)))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    metadata_path = root / ("metadata_" + stamp + ".json")
    stderr_path = root / ("metadata_" + stamp + ".stderr.txt")
    with metadata_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        run = subprocess.run(["ssh", *SSH, "sunboquan-codex", "timeout 110 python3 -"],
                             input=script.encode(), stdout=stdout, stderr=stderr, timeout=120, check=False)
    if run.returncode:
        raise RuntimeError(f"remote metadata exit {run.returncode}; see saved stderr")
    metadata = json.loads(metadata_path.read_bytes())
    if metadata["POTCAR"]["sha256"] != "e3bc41a37d795bfcf1b1dc9a2a9ddfb5ef86aa5dc9aa0ac5a3583471a0982f85":
        raise ValueError("POTCAR differs from original registered input")
    if any(metadata[name]["bytes"] > 64 * 1024 * 1024 for name in FILES):
        raise ValueError("bounded collection size exceeded")
    missing = []
    for name in FILES:
        path = root / name
        if path.exists():
            if sha256_file(path) != metadata[name]["sha256"]:
                raise ValueError("preserve existing mismatched file: " + str(path))
        else:
            missing.append(name)
    if missing:
        sources = ["sunboquan-codex:" + case["directory"] + "/" + name for name in missing]
        transfer = subprocess.run(["scp", "-O", "-C", *SSH, *sources, str(root)],
                                  capture_output=True, timeout=120, check=False)
        (root / "transfer.stderr.txt").write_bytes(transfer.stderr)
        if transfer.returncode:
            raise RuntimeError(f"scp exit {transfer.returncode}; see saved stderr")
    for name in FILES:
        if sha256_file(root / name) != metadata[name]["sha256"]:
            raise ValueError("remote/local hash mismatch: " + name)
    result = {"case": case, "server": "sunboquan-codex", "remote": metadata,
              "remote_metadata_stdout": str(metadata_path), "remote_metadata_sha256": sha256_file(metadata_path),
              "collected_utc": datetime.now(timezone.utc).isoformat(),
              "local_input_hash_matches": {n: sha256_file(Path(case["input"]) / n) == metadata[n]["sha256"]
                                           for n in ("INCAR", "POSCAR", "KPOINTS")},
              "remote_writes": False, "POTCAR_contents_copied": False, "scientifically_accepted": False}
    write_json(receipt, result)
    return result


if __name__ == "__main__":
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for item in CASES:
        print("Collecting existing job " + item["job_id"], flush=True)
        try:
            saved = collect(item)
        except Exception as error:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            write_json(OUTPUT / ("failure_" + stamp + ".json"), {"job_id": item["job_id"], "error": str(error)})
            raise
        print(json.dumps({"job_id": item["job_id"], "verified_files": len(FILES),
                          "original_inputs_match": saved["local_input_hash_matches"]}), flush=True)
