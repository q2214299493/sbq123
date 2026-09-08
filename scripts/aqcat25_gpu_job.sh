#!/bin/bash
#SBATCH --job-name=aqcat25-ads
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gres=gpu:1
#SBATCH --mem=32G
#SBATCH --time=00:20:00
#SBATCH --output=/home/sbq/sbq/aqcat25_ts_pilot/logs/aqcat25-%j.out

set -uo pipefail

PILOT_ROOT=${AQCAT_PILOT_ROOT:-/home/sbq/sbq/aqcat25_ts_pilot}
export AQCAT_PILOT_ROOT="$PILOT_ROOT"
HANDOFF_ROOT=${HANDOFF_ROOT:?HANDOFF_ROOT is required}
SOURCE_HANDOFF_SHA256=${SOURCE_HANDOFF_SHA256:?SOURCE_HANDOFF_SHA256 is required}
DOMAIN_CALIBRATION=${DOMAIN_CALIBRATION:-$PILOT_ROOT/aqcat25_domain_calibration.json}
STARTED_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)

case "$HANDOFF_ROOT" in
  /home/sbq/sbq/*) ;;
  *) echo "HANDOFF_ROOT is outside /home/sbq/sbq" >&2; exit 2 ;;
esac

OUTPUT_ROOT="$HANDOFF_ROOT/output/job_$SLURM_JOB_ID"
EXIT_RECORD="$OUTPUT_ROOT/producer_exit_record.json"
. "$PILOT_ROOT/aqcat25_mz73_env.sh" || exit 2
aqcat25_setup_mz73_environment "$OUTPUT_ROOT"
CHECKPOINT="$AQCAT_ROOT/demo_single/model.pt"

write_exit_record() {
  local exit_code=$1
  STARTED_UTC="$STARTED_UTC" EXIT_CODE="$exit_code" EXIT_RECORD="$EXIT_RECORD" \
    SOURCE_HANDOFF_SHA256="$SOURCE_HANDOFF_SHA256" "$AQCAT_PYTHON" - <<'PY'
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from artifact_io import write_json_atomic

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
write_json_atomic(target, record, ensure_ascii=True)
PY
}

run_pipeline() {
  echo "$SOURCE_HANDOFF_SHA256  $HANDOFF_ROOT/handoff.json" | sha256sum -c - || return $?
  aqcat25_require_mz73 || return $?
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_handoff.py" \
    "$HANDOFF_ROOT/handoff.json" --root "$HANDOFF_ROOT" \
    --schema "$PILOT_ROOT/aqcat25_handoff.schema.json" || return $?
  "$AQCAT_PYTHON" "$PILOT_ROOT/relax_endpoint_candidates.py" \
    --checkpoint "$CHECKPOINT" \
    --handoff "$HANDOFF_ROOT/handoff.json" \
    --output "$OUTPUT_ROOT"
}

build_result_manifest() {
  HANDOFF_ROOT="$HANDOFF_ROOT" OUTPUT_ROOT="$OUTPUT_ROOT" EXIT_RECORD="$EXIT_RECORD" \
    DOMAIN_CALIBRATION="$DOMAIN_CALIBRATION" SOURCE_HANDOFF_SHA256="$SOURCE_HANDOFF_SHA256" \
    CHECKPOINT="$CHECKPOINT" "$AQCAT_PYTHON" - <<'PY'
import os
import socket
from pathlib import Path
from artifact_io import load_json_object, sha256_file, sha256_text, write_json_atomic


def poscar_symbols(path):
    lines = path.read_text(encoding="utf-8").splitlines()
    return [symbol for symbol, count in zip(lines[5].split(), map(int, lines[6].split())) for _ in range(count)]


handoff_root = Path(os.environ["HANDOFF_ROOT"])
output_root = Path(os.environ["OUTPUT_ROOT"])
handoff_path = handoff_root / "handoff.json"
handoff = load_json_object(handoff_path)
result = load_json_object(output_root / "result.json")
structure_path = output_root / "POSCAR"
symbols = poscar_symbols(structure_path)
order_sha = sha256_text("\n".join(symbols) + "\n")

calibration_path = Path(os.environ["DOMAIN_CALIBRATION"])
if calibration_path.is_file():
    calibration = load_json_object(calibration_path)
    reasons = list(calibration.get("scope_failures", []))
    failed_checks = [name for name, passed in calibration.get("threshold_checks", {}).items() if not passed]
    reasons.extend(f"failed force threshold: {name}" for name in failed_checks)
    status = calibration["status"]
    scope = calibration.get("reference_scope", {})
    if status == "in_domain":
        fe_count = symbols.count("Fe")
        adsorbate_count = len(symbols) - fe_count
        lower, upper = scope["adsorbate_atom_count_range"]
        candidate_failures = []
        if fe_count != scope["required_fe_count"]:
            candidate_failures.append(f"candidate Fe count {fe_count}")
        if not set(symbols) <= set(scope["allowed_elements"]):
            candidate_failures.append("candidate contains unsupported elements")
        if not lower <= adsorbate_count <= upper:
            candidate_failures.append(f"candidate adsorbate atom count {adsorbate_count}")
        if candidate_failures:
            status = "out_of_domain"
            reasons.extend(candidate_failures)
    domain = {
        "calibration_id": calibration["calibration_id"],
        "status": status,
        "method": calibration["uncertainty_method"],
        "reasons": reasons or ["compatible Fe45 composition envelope and all empirical force thresholds passed"],
    }
else:
    domain = {
        "calibration_id": None,
        "status": "uncalibrated",
        "method": "no compatible calibration file available",
        "reasons": ["AQCat25 checkpoint has not passed the project force-error gate"],
    }

exit_record = Path(os.environ["EXIT_RECORD"])
manifest = {
    "schema_version": 2,
    "direction": "gpu_to_work",
    "handoff_id": handoff["handoff_id"],
    "workflow_kind": handoff["workflow_kind"],
    "source_workflow_sha256": handoff["source_workflow_sha256"],
    "source_handoff": {"path": "handoff.json", "sha256": os.environ["SOURCE_HANDOFF_SHA256"]},
    "candidate_structure": {
        "path": str(structure_path.relative_to(handoff_root)),
        "sha256": sha256_file(structure_path),
        "format": "vasp_poscar",
        "atom_count": len(symbols),
        "atom_order_sha256": order_sha,
    },
    "adsorption": handoff["adsorption"],
    "producer": {
        "backend": "aqcat_gpu",
        "hostname": socket.gethostname(),
        "gpu_job_id": os.environ["SLURM_JOB_ID"],
        "model_identifier": handoff["model"]["identifier"],
        "checkpoint_sha256": sha256_file(Path(os.environ["CHECKPOINT"])),
    },
    "result": {
        "result_class": "predicted_adsorption_candidate_only",
        "optimizer_status": "converged" if result["converged"] else "unfinished",
        "optimizer_steps": result["optimizer_steps"],
        "predicted_energy": {"value": result["energy_eV"], "unit": "eV", "reportable_dft": False},
        "predicted_force": {"fmax": result["movable_fmax_eV_per_A"], "unit": "eV/A", "reportable_dft": False},
        "geometry_before": result["geometry_before"],
        "geometry_after": result["geometry_after"],
        "connectivity_status": result["connectivity"]["status"],
        "structure_invariants": result["structure_invariants"],
    },
    "domain_assessment": domain,
    "producer_exit_record": {
        "path": str(exit_record.relative_to(handoff_root)),
        "sha256": sha256_file(exit_record),
        "status": "success",
        "exit_code": 0,
        "evidence_class": "producer_process_only_not_scheduler_accounting",
    },
    "restrictions": handoff["restrictions"],
}
write_json_atomic(output_root / "gpu_result_manifest.json", manifest, ensure_ascii=True)
PY
  local build_code=$?
  [ "$build_code" -eq 0 ] || return "$build_code"
  "$AQCAT_PYTHON" "$PILOT_ROOT/aqcat25_handoff.py" \
    "$OUTPUT_ROOT/gpu_result_manifest.json" --root "$HANDOFF_ROOT" \
    --schema "$PILOT_ROOT/aqcat25_handoff.schema.json"
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
