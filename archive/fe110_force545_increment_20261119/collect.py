"""Collect bound evidence for the nine completed LSF statics into a new local directory."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
import re
import shlex
import subprocess
import tarfile

import numpy as np
from ase.io import read
from scripts.adsorption.reico_probe_review import validate_static
from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive

root = Path("calculations/fe110_reico_pilot300_20261022/c2_c3_label9_lsf_20261118_v1")
out = root.parent / "force545_increment9_20261119_v2"
out.mkdir(exist_ok=False)
plan = load_json_object(root / "final_submission_list.json")
assert sha256_file(root / "final_submission_list.json") == "4ac145dc610571030b1738bef87f5b4b6be0190c0ce49104bbf1eea93537b388"
jobs = {x["id"]: x["job_id"] for x in load_json_object(root / "execution_20261118_v1/scheduler_verified.json")["jobs"]}
assert plan["backend"] == "sunboquan-codex"
assert len(jobs) == len(plan["jobs"]) == 9
base = "sbq/Fe110/reico_c2_c3_label9_20261118_v1"
files = ("POSCAR", "INCAR", "KPOINTS", "POTCAR.spec", "script.lsf", "OSZICAR", "OUTCAR", "CONTCAR")
for r in plan["jobs"]:
    assert re.fullmatch(r"family_\d{4}_step\d{3}", r["id"])
    assert re.fullmatch(r"[1-9]\d*", jobs[r["id"]])
    assert r["remote_directory"] == f"~/{base}/{r['id']}"
paths = {f"{sid}/{name}" for sid in jobs for name in files}
ssh = ["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8", "--", plan["backend"]]


def query(cmd):
    p = subprocess.run([*ssh, cmd], capture_output=True, timeout=55)
    if p.returncode:
        raise RuntimeError(p.stderr.decode("utf-8", "replace")[:300])
    return p.stdout


with ThreadPoolExecutor(max_workers=2) as pool:
    evidence = pool.submit(
        query,
        f"cd ~/{base} && sha256sum "
        + shlex.join([f"{sid}/POTCAR" for sid in jobs])
        + " && printf '\\n---LSF---\\n' && bjobs -a -UF "
        + " ".join(jobs.values()),
    )
    bundle = pool.submit(query, f"cd ~/{base} && tar -czf - -- " + shlex.join(sorted(paths)))
    evidence_bytes = evidence.result()
    hashes, schedule = evidence_bytes.decode("utf-8").split("---LSF---", 1)
    with (out / "remote_terminal_and_potcar.stdout").open("xb") as stream:
        stream.write(evidence_bytes)
    compact = bundle.result()
assert len(compact) < 8 * 1024 * 1024
potcars = dict(
    (path, digest)
    for digest, path in (line.split() for line in hashes.splitlines() if re.fullmatch(r"[a-f0-9]{64}  family_\d{4}_step\d{3}/POTCAR", line))
)
records = re.split(r"(?m)(?=^Job <[1-9]\d*>,)", schedule)
records = {re.match(r"Job <(\d+)>", x)[1]: x for x in records if x.startswith("Job <")}
assert len(potcars) == len(records) == 9
fmt = "%a %b %d %H:%M:%S %Y"
checked = 0
durations = []
scratch = out / "source_evidence"
scratch.mkdir()
with tarfile.open(fileobj=BytesIO(compact), mode="r:gz") as tar:
    seen = set()
    for m in tar:
        assert m.isfile() and m.size < 1024 * 1024 and m.name in paths and m.name not in seen
        seen.add(m.name)
        path = Path(scratch) / m.name
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(tar.extractfile(m).read())
    assert seen == paths
    label_rows = []
    for r in plan["jobs"]:
        sid = r["id"]
        job = jobs[sid]
        directory = Path(scratch) / sid
        scope = {"id": sid, "job": job, "composition": r["composition"]}
        try:
            record = records[job]
            assert "Status <DONE>, Queue <Gkn_normal>" in record and f"{base}/{sid}" in record, "scheduler binding"
            start = re.search(r"^(.+?): Started on 32 Hosts/Processors", record, re.M)
            end = re.search(r"^(.+?): Done successfully\. The CPU time used is ([0-9.]+) seconds", record, re.M)
            if start and end:
                sec = (datetime.strptime(end[1], fmt) - datetime.strptime(start[1], fmt)).total_seconds()
                durations.append(sec)
                scope.update(wall_min=round(sec / 60, 2), end=end[1], cpu_core_hours=round(float(end[2]) / 3600, 3))
            assert potcars[f"{sid}/POTCAR"] == r["POTCAR_sha256"], "POTCAR differs"
            for name, digest in r["input_sha256"].items():
                assert sha256((directory / name).read_bytes()).hexdigest() == digest, name + " hash mismatch"
            folder = Path(r["local_input_directory"])
            receipt = load_json_object(folder / "submission_record.json")
            assert receipt["job_id"] == job and receipt["server_alias"] == plan["backend"], "submission receipt job binding"
            assert receipt["remote_dir"] == r["remote_directory"] and receipt["bundle_sha256"] == r["bundle_sha256"], (
                "target or input binding"
            )
            assert receipt["gate_decision_sha256"] == sha256_file(folder / "execution_decision.json"), "decision binding"
            assert receipt["potcar_sha256"] == r["POTCAR_sha256"], "POTCAR submission binding"
            local = folder / "POSCAR"
            assert sha256(local.read_bytes()).hexdigest() == r["input_sha256"]["POSCAR"], "Local POSCAR changed"
            label = validate_static(directory, read(local, format="vasp").get_chemical_symbols())
            force = np.linalg.norm(np.asarray(label["forces_eV_per_A"]), axis=1)
            scope.update(
                scf_iterations=label["SCF"]["last_electronic_iteration"],
                position_delta_A=label["max_coordinate_difference_A"],
                Fe_moment_range_muB=label["Fe_moment_range_muB"],
                total_moment_muB=label["total_magnetization_muB"],
                Fe_positive_moments=label["Fe_positive_moment_count"],
                ads_fmax=round(float(force[45:].max()), 5),
                Fe_movable_fmax=round(float(force[18:45].max()), 5),
                fmax=round(float(force[18:].max()), 5),
            )
            if label["Fe_positive_moment_count"] != 45:
                raise ValueError("Nonpositive Fe local moment")
            label_doc = {
                **label,
                "sample_id": sid,
                "source_job_id": job,
                "source_POSCAR_sha256": sha256_file(directory / "POSCAR"),
                "source_OUTCAR_sha256": sha256_file(directory / "OUTCAR"),
                "source_OSZICAR_sha256": sha256_file(directory / "OSZICAR"),
                "source_CONTCAR_sha256": sha256_file(directory / "CONTCAR"),
                "source_submission_receipt_sha256": sha256_file(folder / "submission_record.json"),
                "source_POTCAR_sha256": potcars[f"{sid}/POTCAR"],
                "source_terminal_status": "DONE",
                "reportable_final_energy": False,
                "training_authorized": False,
            }
            label_path = directory / "label_review.json"
            write_json_exclusive(label_path, label_doc)
            label_rows.append(
                {
                    "id": sid,
                    "job": job,
                    "label_path": label_path.relative_to(out).as_posix(),
                    "label_sha256": sha256_file(label_path),
                    "source_files": {name: sha256_file(directory / name) for name in files},
                }
            )
            checked += 1
        except (OSError, ValueError, AssertionError) as exc:
            scope["verification_error"] = str(exc)
        print(json.dumps(scope, ensure_ascii=False), flush=True)
if checked != 9:
    raise RuntimeError("Incomplete reviewed label collection. Preserve evidence.")
write_json_exclusive(
    out / "source_collection.json",
    {
        "host": plan["backend"],
        "terminal_evidence_sha256": sha256_file(out / "remote_terminal_and_potcar.stdout"),
        "final_submission_list_sha256": sha256_file(root / "final_submission_list.json"),
        "records": label_rows,
        "POTCAR_content_copied": False,
    },
)
print("LOCAL_QC_PASSES", checked)
if len(durations) == 9:
    print("ALLOCATED_CORE_HOURS", round(sum(durations) * 32 / 3600, 3))
