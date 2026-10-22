"""Read-only remote diagnosis;Python3.6 compatible;never submit or change targets."""
import argparse
import hashlib
import json
import os
import subprocess


def command(argv):
    response = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=20)
    if len(response.stdout.encode("utf-8")) > 131072:
        raise ValueError("diagnostic output exceeds131072bytes")
    return {"returncode": response.returncode, "stdout": response.stdout, "stderr": response.stderr}


def inspect(payload):
    result = {"targets": []}
    for row in payload["affected"]:
        directory = os.path.expanduser(row["remote_dir"])
        item = {"sample_id": row["sample_id"], "directory_exists": os.path.isdir(directory),
                "hashes": {}, "outputs_present": []}
        expected_files = dict(row["files"], POTCAR=row["potcar_sha256"])
        for name, expected in expected_files.items():
            path = os.path.join(directory, name)
            if os.path.isfile(path):
                with open(path, "rb") as handle:
                    actual = hashlib.sha256(handle.read()).hexdigest()
                item["hashes"][name] = {"sha256": actual, "matches": actual == expected}
            else:
                item["hashes"][name] = {"exists": False, "matches": False}
        lock = directory + ".submission-reservation/reservation_id"
        if os.path.isfile(lock):
            with open(lock) as handle:
                item["reservation_matches"] = handle.read().strip() == row["reservation_id"]
        for name in ("OUTCAR", "OSZICAR", "vasp.out"):
            if os.path.isfile(os.path.join(directory, name)):
                item["outputs_present"].append(name)
        result["targets"].append(item)
    query = command(["bjobs", "-a"])
    result["all_account_bjobs"] = query
    known = set(payload["receipted_ids"])
    rows = [line.split() for line in query["stdout"].splitlines()
            if line.split() and line.split()[0].isdigit()]
    result["unmatched_active_job_ids"] = [row[0] for row in rows if row[2] in ("RUN", "PEND") and row[0] not in known]
    result["unmatched_recent_job_ids"] = [row[0] for row in rows if row[0] not in known
                                          and int(row[0]) >= min(int(value) for value in known)]
    processes = command(["ps", "-u", "nsgkn_chengdj3", "-o", "pid,ppid,stat,args"])
    result["process_query_returncode"] = processes["returncode"]
    names = [row["sample_id"] for row in payload["affected"]]
    result["matching_submission_processes"] = [line for line in processes["stdout"].splitlines()
                                                if any(name in line for name in names)]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("request")
    arguments = parser.parse_args()
    with open(arguments.request) as source:
        request = json.load(source)
    print(json.dumps(inspect(request)))
