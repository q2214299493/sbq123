#!/bin/bash
#SBATCH --job-name=aqcat-co-ts
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=/home/sbq/sbq/aqcat25_ts_pilot/reactions/co_dissociation_fe/topic1_20260719/logs/aqcat-ts-%j.out

set -uo pipefail

PILOT_ROOT=/home/sbq/sbq/aqcat25_ts_pilot
TASK_ROOT=$PILOT_ROOT/reactions/co_dissociation_fe/topic1_20260719
HANDOFF=$TASK_ROOT/gpu_handoff/handoff.json
SOURCE_HANDOFF_SHA256=${SOURCE_HANDOFF_SHA256:?SOURCE_HANDOFF_SHA256 is required}
OUTPUT_ROOT=$TASK_ROOT/output/job_$SLURM_JOB_ID
EXIT_RECORD=$OUTPUT_ROOT/producer_exit_record.json
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

. "$PILOT_ROOT/aqcat25_mz73_env.sh" || exit 2
aqcat25_setup_mz73_environment "$OUTPUT_ROOT"
CHECKPOINT=${CHECKPOINT:-$AQCAT_ROOT/demo_single/model.pt}

write_exit_record() {
  local exit_code=$1
  STARTED_UTC=$STARTED_UTC EXIT_CODE=$exit_code EXIT_RECORD=$EXIT_RECORD \
    SOURCE_HANDOFF_SHA256=$SOURCE_HANDOFF_SHA256 "$AQCAT_PYTHON" - <<'PY'
import json
import os
import socket
from datetime import datetime, timezone
from pathlib import Path

target = Path(os.environ["EXIT_RECORD"])
exit_code = int(os.environ["EXIT_CODE"])
record = {
    "gpu_job_id": os.environ["SLURM_JOB_ID"],
    "hostname": socket.gethostname(),
    "started_utc": os.environ["STARTED_UTC"],
    "finished_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    "exit_code": exit_code,
    "status": "success" if exit_code == 0 else "failed",
    "source_handoff_sha256": os.environ["SOURCE_HANDOFF_SHA256"],
    "evidence_class": "producer_process_only_not_scheduler_accounting",
}
temporary = target.with_suffix(".json.tmp")
temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
temporary.replace(target)
PY
}

run_pipeline() {
  echo "$SOURCE_HANDOFF_SHA256  $HANDOFF" | sha256sum -c - || return $?
  test "$(hostname)" = MZ73 || return $?
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_handoff.py" "$HANDOFF" \
    --root "$TASK_ROOT" --schema "$PILOT_ROOT/aqcat25_handoff.schema.json" || return $?
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat_ts_pilot.py" \
    --stage ts \
    --is "$TASK_ROOT/matched_statics/IS/POSCAR" \
    --waypoint "$TASK_ROOT/gpu_handoff/waypoints/WP_01/POSCAR" \
    --waypoint "$TASK_ROOT/gpu_handoff/waypoints/WP_02/POSCAR" \
    --waypoint "$TASK_ROOT/gpu_handoff/waypoints/WP_03/POSCAR" \
    --fs "$TASK_ROOT/matched_statics/FS/POSCAR" \
    --checkpoint "$CHECKPOINT" \
    --bond break:46:47 \
    --adsorbate-indices 46,47 \
    --n-images-per-segment 8 \
    --fmax-ml 0.05 \
    --max-steps 300 \
    --min-steps 10 \
    --output-dir "$OUTPUT_ROOT"
}

build_result_manifest() {
  TASK_ROOT=$TASK_ROOT OUTPUT_ROOT=$OUTPUT_ROOT EXIT_RECORD=$EXIT_RECORD HANDOFF=$HANDOFF \
    CHECKPOINT=$CHECKPOINT SOURCE_HANDOFF_SHA256=$SOURCE_HANDOFF_SHA256 "$AQCAT_PYTHON" - <<'PY'
import hashlib
import json
import os
import socket
from pathlib import Path

import numpy as np
from ase.constraints import FixAtoms
from ase.io import read


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixed_indices(atoms):
    result = set()
    for constraint in atoms.constraints:
        if isinstance(constraint, FixAtoms):
            result.update(int(index) for index in constraint.get_indices())
    return sorted(result)


def geometry(atoms):
    symbols = atoms.get_chemical_symbols()
    c = symbols.index("C")
    o = symbols.index("O")
    fe = [index for index, symbol in enumerate(symbols) if symbol == "Fe"]
    c_fe = min(atoms.get_distance(c, index, mic=True) for index in fe)
    o_fe = min(atoms.get_distance(o, index, mic=True) for index in fe)
    distances = atoms.get_all_distances(mic=True)
    np.fill_diagonal(distances, np.inf)
    distances[c, o] = distances[o, c] = np.inf
    return {
        "co_distance_A": float(atoms.get_distance(c, o, mic=True)),
        "c_fe_distance_A": float(c_fe),
        "o_fe_distance_A": float(o_fe),
        "minimum_unintended_contact_A": float(np.min(distances)),
    }


task_root = Path(os.environ["TASK_ROOT"])
output_root = Path(os.environ["OUTPUT_ROOT"])
handoff_path = Path(os.environ["HANDOFF"])
handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
report = json.loads((output_root / "pilot_report.json").read_text(encoding="utf-8"))
guess = read(output_root / "TS_GUESS.vasp", format="vasp")
candidate = read(output_root / "TS_CANDIDATE.vasp", format="vasp")
initial = read(task_root / "matched_statics/IS/POSCAR", format="vasp")
symbols = candidate.get_chemical_symbols()
order_sha = hashlib.sha256(("\n".join(symbols) + "\n").encode("utf-8")).hexdigest()
fixed = fixed_indices(initial)
fixed_preserved = fixed == fixed_indices(candidate) and np.allclose(
    initial.positions[fixed], candidate.positions[fixed], atol=1e-6, rtol=0.0
)
candidate_status = str(report.get("candidate_status", "unfinished")).lower()
optimizer_status = "converged" if candidate_status in {"converged", "finished"} else "unfinished"
exit_record = Path(os.environ["EXIT_RECORD"])
candidate_path = output_root / "TS_CANDIDATE.vasp"
manifest = {
    "schema_version": 2,
    "direction": "gpu_to_work",
    "handoff_id": handoff["handoff_id"],
    "workflow_kind": handoff["workflow_kind"],
    "source_workflow_sha256": handoff["source_workflow_sha256"],
    "source_handoff": {
        "path": str(handoff_path.relative_to(task_root)),
        "sha256": os.environ["SOURCE_HANDOFF_SHA256"],
    },
    "candidate_structure": {
        "path": str(candidate_path.relative_to(task_root)),
        "sha256": sha256(candidate_path),
        "format": "vasp_poscar",
        "atom_count": len(symbols),
        "atom_order_sha256": order_sha,
    },
    "transition_state": handoff["transition_state"],
    "producer": {
        "backend": "aqcat_gpu",
        "hostname": socket.gethostname(),
        "gpu_job_id": os.environ["SLURM_JOB_ID"],
        "model_identifier": handoff["model"]["identifier"],
        "checkpoint_sha256": sha256(Path(os.environ["CHECKPOINT"])),
    },
    "result": {
        "result_class": "predicted_transition_state_candidate_only",
        "optimizer_status": optimizer_status,
        "optimizer_steps": int(report.get("optimizer_steps", 0)),
        "predicted_energy": {
            "value": float(report["candidate_energy_ml_eV"]),
            "unit": "eV",
            "reportable_dft": False,
        },
        "predicted_force": {
            "fmax": float(report["candidate_fmax_ml_ev_per_angstrom"]),
            "unit": "eV/A",
            "reportable_dft": False,
        },
        "geometry_before": geometry(guess),
        "geometry_after": geometry(candidate),
        "connectivity_status": "not_applicable",
        "structure_invariants": {
            "atom_order_preserved": symbols == initial.get_chemical_symbols(),
            "cell_preserved": bool(np.allclose(candidate.cell.array, initial.cell.array, atol=1e-6, rtol=0.0)),
            "fixed_atoms_preserved": bool(fixed_preserved),
        },
    },
    "domain_assessment": {
        "calibration_id": None,
        "status": "uncalibrated",
        "method": "no compatible off-equilibrium or saddle force-label calibration",
        "reasons": ["AQCat25 Fe45 calibration covers near-relaxed adsorption structures only"],
    },
    "producer_exit_record": {
        "path": str(exit_record.relative_to(task_root)),
        "sha256": sha256(exit_record),
        "status": "success",
        "exit_code": 0,
        "evidence_class": "producer_process_only_not_scheduler_accounting",
    },
    "restrictions": handoff["restrictions"],
}
(output_root / "gpu_result_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
PY
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_handoff.py" "$OUTPUT_ROOT/gpu_result_manifest.json" \
    --root "$TASK_ROOT" --schema "$PILOT_ROOT/aqcat25_handoff.schema.json"
}

exit_code=0
run_pipeline || exit_code=$?
write_exit_record "$exit_code"
if [ "$exit_code" -eq 0 ]; then
  build_result_manifest || exit_code=$?
  if [ "$exit_code" -ne 0 ]; then
    write_exit_record "$exit_code"
  fi
fi
exit "$exit_code"
