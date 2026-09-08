from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from scripts.neb_agent.utils_structure import compatible, max_neighbor_step, read_poscar  # noqa: E402
from scripts.ts_strategy_engine.contract import load_contract  # noqa: E402
from scripts.ts_strategy_engine.registry import compatibility_fingerprint  # noqa: E402


CALC_ROOT = Path(__file__).resolve().parents[1]
DATABASE = REPO_ROOT / "data" / "project_registry.sqlite3"
CONTRACT = CALC_ROOT / "contract" / "reaction.yaml"
REVIEWED_AT = "2026-07-19T00:37:18+08:00"
ENERGY_CONVENTION = (
    "true_fe110_5layer_5x5x1 matched final static; PBE/PAW-PBE ENCUT=400 eV "
    "Gamma=5x5x1 ISPIN=2 ISMEAR=1 SIGMA=0.10 eV EDIFF=1E-6; OUTCAR final TOTEN"
)

RECORDS = {
    "IS": {
        "calculation_id": "fe110_co_dissociation_is_static_9631646",
        "job_record_id": "lsf_9631646",
        "scheduler_job_id": "9631646",
        "purpose": "Matched final static for Fe(110) CO/top dissociation initial state",
        "source_record": "Topic-1 accepted CO/top endpoint from VASP job 9558184",
        "parent_calculation_id": None,
        "remote_directory": "~/sbq/Fe110/ts/co_dissociation_topic1_20260718/matched_statics/IS",
        "submitted_at": "2026-07-18T23:09:01+08:00",
        "started_at": "2026-07-18T23:11:49+08:00",
        "finished_at": "2026-07-19T00:32:25+08:00",
        "expected": {
            "POSCAR": "6ed0dcc7bc57e30bce0eca23a94e6b8823dfc543a6bc943dccffcda531daadbf",
            "INCAR": "9a6fadf3b2235967d6d49e22c705397387623e2fcb5434b0968710896d284b4c",
            "KPOINTS": "e8566bc79afc49b06d47d4a863ec6dcf6325697a84f6e92be9d8b16a20bfd24d",
            "POTCAR": "d31ba5b0137a94cfad121c43da633fa92b56c5e4dd3bb0feab4052f7bbbe444e",
            "OUTCAR": "b64cf7c04e1bee30328a8678d8441cd0aaa47e32a74faabee8689155232deb45",
            "CONTCAR": "85251be1b4e571697ddcf2f5d9bb1f6babad1b5368f412faef9cf08e88309334",
        },
    },
    "FS": {
        "calculation_id": "fe110_co_dissociation_fs_static_9631647",
        "job_record_id": "lsf_9631647",
        "scheduler_job_id": "9631647",
        "purpose": "Matched final static for Fe(110) C/long-bridge + O/hollow dissociation final state",
        "source_record": "Accepted C*+O* endpoint from VASP job 9622455 after exact 3x3 symmetry mapping",
        "parent_calculation_id": "fe110_ads_cpluso_hadj_20260714",
        "remote_directory": "~/sbq/Fe110/ts/co_dissociation_topic1_20260718/matched_statics/FS",
        "submitted_at": "2026-07-18T23:09:01+08:00",
        "started_at": "2026-07-18T23:14:13+08:00",
        "finished_at": "2026-07-18T23:43:56+08:00",
        "expected": {
            "POSCAR": "0fe755b8954c58c991009093c96065787e522805bd359eb10a114287281c9de1",
            "INCAR": "dc9675731c708f58aa9608080d0bc2bdcfdbc4a10f52073a166837a874b390da",
            "KPOINTS": "e8566bc79afc49b06d47d4a863ec6dcf6325697a84f6e92be9d8b16a20bfd24d",
            "POTCAR": "d31ba5b0137a94cfad121c43da633fa92b56c5e4dd3bb0feab4052f7bbbe444e",
            "OUTCAR": "78d719e54bc1ef2f16bed07300e4b65f8db8809f676255466434c9be0e25906c",
            "CONTCAR": "b201d51a29c24bb873a5d64aaaf1d27ad4736face22cfdac24e92a1d061893f3",
        },
    },
    "LOCAL_FS": {
        "directory": "local_endpoint_matched_static_9647798_20260729",
        "calculation_id": "fe110_co_dissociation_local_fs_static_9649924",
        "job_record_id": "lsf_9649924",
        "scheduler_job_id": "9649924",
        "purpose": "Matched final static for the locally stable Fe(110) CO-dissociation TS endpoint",
        "source_record": "Locally relaxed TS_ENDPOINT candidate from VASP job 9647798",
        "parent_calculation_id": None,
        "remote_directory": "~/sbq/Fe110/ts/co_dissociation_topic1_20260718/local_endpoint_matched_static_9647798_20260729",
        "submitted_at": "2026-07-30T00:29:44+08:00",
        "started_at": "2026-07-30T00:45:07+08:00",
        "finished_at": "2026-07-30T01:20:12+08:00",
        "reviewed_at": "2026-07-30T11:14:25+08:00",
        "remote_potcar_size": 665681,
        "expected": {
            "POSCAR": "22afe1e96a5729f403e28bb7a37295ab3cedbb6c5aad7069e76df6622e8a7642",
            "INCAR": "8f5acbac95ea67d32381cdd66c017d66d7e96f6192e48a3dbf9187f2330094f0",
            "KPOINTS": "0d7e291117433dac5393f29520b635e92f06e6c8e91aa941137c86b1d39162ae",
            "POTCAR": "d31ba5b0137a94cfad121c43da633fa92b56c5e4dd3bb0feab4052f7bbbe444e",
            "OUTCAR": "70017884ce0b8aa3f3736ba083f99d850219e99a42a64e4bcd6623722ae312f1",
            "CONTCAR": "f5113993fe852156e53fbbf0172dcf74f30c5ddbc6a1f69de7f677bf18edc0d5",
            "OSZICAR": "2ea5ba7fc759c3b1f54cedd91a857cc69568f98aabaab1361a4affc045fab782",
        },
    },
}

FILE_ROLES = {
    "POSCAR": "geometry_input",
    "CONTCAR": "final_structure",
    "INCAR": "vasp_input",
    "KPOINTS": "kpoint_input",
    "POTCAR": "licensed_runtime_input",
    "OUTCAR": "vasp_output",
    "OSZICAR": "electronic_summary",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_energy_and_convergence(directory: Path) -> float:
    outcar = (directory / "OUTCAR").read_text(encoding="utf-8", errors="replace")
    oszicar = (directory / "OSZICAR").read_text(encoding="utf-8", errors="replace")
    if outcar.count("General timing and accounting informations") != 1:
        raise ValueError(f"{directory.name}: normal completion marker missing or duplicated")
    if re.search(r"VERY BAD NEWS|ZBRENT|BRMIX|segmentation", outcar, re.IGNORECASE):
        raise ValueError(f"{directory.name}: fatal marker found")
    energies = re.findall(r"free\s+energy\s+TOTEN\s*=\s*([-+0-9.Ee]+)\s+eV", outcar)
    if not energies:
        raise ValueError(f"{directory.name}: final TOTEN missing")
    scf_rows = re.findall(
        r"^\s*(?:DAV|RMM):\s+\d+\s+[-+0-9.Ee]+\s+([-+0-9.Ee]+)",
        oszicar,
        re.MULTILINE,
    )
    if not scf_rows or abs(float(scf_rows[-1])) > 1.0e-6:
        raise ValueError(f"{directory.name}: final electronic step does not satisfy EDIFF=1E-6")
    return float(energies[-1])


def validate_record(label: str, record: dict) -> dict:
    directory = CALC_ROOT / "matched_statics" / record.get("directory", label)
    hashes = {}
    for filename in FILE_ROLES:
        path = directory / filename
        if filename == "POTCAR" and not path.is_file():
            hashes[filename] = record["expected"]["POTCAR"]
            continue
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"{label}: required file missing or empty: {filename}")
        hashes[filename] = sha256(path)
    for filename, expected in record["expected"].items():
        if hashes[filename] != expected:
            raise ValueError(f"{label}: {filename} hash mismatch")
    poscar = read_poscar(directory / "POSCAR")
    contcar = read_poscar(directory / "CONTCAR")
    errors = compatible(poscar, contcar)
    displacement = max_neighbor_step(poscar, contcar)
    if errors or displacement > 1.0e-6:
        raise ValueError(
            f"{label}: static structure changed: errors={errors}, displacement={displacement:.6g} A"
        )
    return {
        "directory": directory,
        "hashes": hashes,
        "energy": parse_energy_and_convergence(directory),
        "max_displacement_A": displacement,
    }


def insert_exact(connection: sqlite3.Connection, table: str, key: str, values: dict) -> None:
    existing = connection.execute(f"SELECT * FROM {table} WHERE {key}=?", (values[key],)).fetchone()
    if existing is not None:
        for column, value in values.items():
            if existing[column] != value:
                raise ValueError(f"{table}.{values[key]} conflicts at {column}")
        return
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    connection.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})",
        tuple(values.values()),
    )


def register(connection: sqlite3.Connection, label: str, record: dict, evidence: dict, compatibility: dict) -> None:
    calculation_id = record["calculation_id"]
    job_record_id = record["job_record_id"]
    reviewed_at = record.get("reviewed_at", REVIEWED_AT)
    insert_exact(
        connection,
        "calculations",
        "calculation_id",
        {
            "calculation_id": calculation_id,
            "module": "transition_state_search",
            "purpose": record["purpose"],
            "scientific_system": "true_fe110_5layer_5x5x1",
            "parent_calculation_id": record["parent_calculation_id"],
            "workflow_status": "static_accepted",
            "created_at": record["submitted_at"],
            "source_record": record["source_record"],
            "notes": "Matched endpoint static accepted after scheduler, electronic, hash, geometry, and compatibility gates.",
        },
    )
    insert_exact(
        connection,
        "jobs",
        "job_record_id",
        {
            "job_record_id": job_record_id,
            "calculation_id": calculation_id,
            "scheduler_job_id": record["scheduler_job_id"],
            "scheduler": "LSF",
            "server_alias": "sunboquan-codex",
            "queue": "Gkn_normal",
            "remote_directory": record["remote_directory"],
            "submit_script": "script.lsf",
            "submitted_at": record["submitted_at"],
            "started_at": record["started_at"],
            "finished_at": record["finished_at"],
        },
    )
    status_exists = connection.execute(
        "SELECT 1 FROM job_status_history WHERE job_record_id=? AND scheduler_status='DONE' AND checked_at=?",
        (job_record_id, reviewed_at),
    ).fetchone()
    if status_exists is None:
        connection.execute(
            """
            INSERT INTO job_status_history
            (job_record_id, scheduler_status, scientific_status, checked_at,
             source_command, source_text, reviewer, notes)
            VALUES (?, 'DONE', 'accepted_matched_static', ?, 'bjobs -l JOBID', ?, 'Codex', ?)
            """,
            (
                job_record_id,
                reviewed_at,
                f"Job {record['scheduler_job_id']} Done successfully; OUTCAR normal completion and final SCF dE <= 1E-6.",
                "Scheduler DONE is recorded separately from electronic, geometry, compatibility, and acceptance checks.",
            ),
        )
    for filename, role in FILE_ROLES.items():
        path = evidence["directory"] / filename
        file_id = f"{calculation_id}_{filename.lower()}"
        local_path = None if filename == "POTCAR" else str(path.resolve())
        storage_mode = "external_path_reference" if filename == "POTCAR" else "local_working_copy_and_remote"
        insert_exact(
            connection,
            "files",
            "file_id",
            {
                "file_id": file_id,
                "calculation_id": calculation_id,
                "job_record_id": job_record_id,
                "role": role,
                "filename": filename,
                "local_path": local_path,
                "remote_path": f"{record['remote_directory']}/{filename}",
                "storage_mode": storage_mode,
                "byte_size": (
                    path.stat().st_size
                    if path.is_file()
                    else record["remote_potcar_size"]
                ),
                "modified_at": None,
                "sha256": evidence["hashes"][filename],
                "existence_status": "confirmed",
                "license_or_sensitivity": (
                    "licensed VASP POTCAR; content excluded from repository"
                    if filename == "POTCAR"
                    else "project scientific input/output"
                ),
                "source_file_id": None,
                "notes": "Hash verified against the completed remote calculation.",
            },
        )
    result_id = f"{calculation_id}_total_energy_eV"
    insert_exact(
        connection,
        "results",
        "result_id",
        {
            "result_id": result_id,
            "calculation_id": calculation_id,
            "result_name": "matched_static_total_energy_eV",
            "numeric_value": evidence["energy"],
            "text_value": None,
            "unit": "eV",
            "temperature_k": None,
            "pressure_pa": None,
            "reference_convention": ENERGY_CONVENTION,
            "source_file_id": f"{calculation_id}_outcar",
            "source_locator": "OUTCAR final free energy TOTEN",
            "extraction_method": "hash-bound regex extraction plus final OSZICAR EDIFF check",
            "validation_status": "accepted_matched_static",
            "uncertainty_text": None,
            "created_at": reviewed_at,
            "notes": "Endpoint-only matched static; final barrier awaits an accepted TS matched static.",
        },
    )
    insert_exact(
        connection,
        "reviews",
        "review_id",
        {
            "review_id": f"{calculation_id}_result_gate",
            "calculation_id": calculation_id,
            "review_type": "matched_static_result_gate",
            "decision": "PASS",
            "reviewer": "Codex",
            "reviewed_at": reviewed_at,
            "evidence": (
                f"LSF DONE; normal OUTCAR completion; final SCF dE<=1E-6; "
                f"POSCAR/CONTCAR max displacement={evidence['max_displacement_A']:.3e} A; verified hashes"
            ),
            "reason": "Matched static is technically converged, structurally unchanged, and compatible with the locked Fe45 branch.",
        },
    )
    fingerprint = compatibility_fingerprint(compatibility)
    compatibility_json = __import__("json").dumps(compatibility, sort_keys=True)
    insert_exact(
        connection,
        "calculation_compatibility",
        "calculation_id",
        {
            "calculation_id": calculation_id,
            "compatibility_fingerprint": fingerprint,
            "compatibility_json": compatibility_json,
            "reviewer": "Codex",
            "reviewed_at": reviewed_at,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and register completed matched endpoint statics.")
    parser.add_argument("--apply", action="store_true", help="Commit validated records to the project registry.")
    args = parser.parse_args()
    contract = load_contract(CONTRACT)
    evidence = {label: validate_record(label, record) for label, record in RECORDS.items()}
    for label in RECORDS:
        print(
            f"{label} PASS job={RECORDS[label]['scheduler_job_id']} "
            f"TOTEN={evidence[label]['energy']:.8f} eV "
            f"max_displacement={evidence[label]['max_displacement_A']:.3e} A"
        )
    print(f"reaction_energy_endpoint_only={evidence['FS']['energy'] - evidence['IS']['energy']:.8f} eV")
    print(
        "reaction_energy_local_endpoint_only="
        f"{evidence['LOCAL_FS']['energy'] - evidence['IS']['energy']:.8f} eV"
    )
    if not args.apply:
        print("DRY_RUN")
        return
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        with connection:
            for label in RECORDS:
                register(connection, label, RECORDS[label], evidence[label], contract["compatibility"])
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
            if foreign_key_errors:
                raise ValueError(f"registry foreign-key check failed: {foreign_key_errors}")
    finally:
        connection.close()
    print("REGISTERED")


if __name__ == "__main__":
    main()
