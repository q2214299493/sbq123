#!/bin/bash
#SBATCH --job-name=c2-ads-bootstrap-probe
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:01:00
#SBATCH --no-requeue

# No Python, model, CUDA call or training entrypoint is permitted in this probe.
set -euo pipefail
PROBE_ROOT=/home/sbq/sbq/adsorption_c2_finetune_20261010_v3/bootstrap_probe_v1
PHASE=entry
finish() {
  code=$?
  trap - EXIT
  printf 'PROBE_EXIT phase=%s code=%d\n' "$PHASE" "$code"
  (umask 077; set -C; printf '{"document_kind":"no_model_bootstrap_probe_exit","job_id":"%s","phase":"%s","exit_code":%d,"model_run":false,"GPU_requested":false}\n' \
    "$SLURM_JOB_ID" "$PHASE" "$code" > "$PROBE_ROOT/exit_$SLURM_JOB_ID.json") || :
  exit "$code"
}
trap finish EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
for variable in PACKAGE_ROOT AUTHORIZATION TMPDIR XDG_CACHE_HOME TORCH_HOME HF_HOME AQCAT_ROOT AQCAT_PILOT_ROOT AQCAT_PYTHON; do
  printf 'INHERITED %s=%q\n' "$variable" "${!variable-UNSET}"
done
PHASE=required_variables
PACKAGE_ROOT=${PACKAGE_ROOT:?explicit package root required}
AUTHORIZATION=${AUTHORIZATION:?explicit authorization path required}
PHASE=lexical_package_boundary
case "$PACKAGE_ROOT" in /home/sbq/sbq/*) ;; *) exit 2 ;; esac
PHASE=source_environment
source "$PACKAGE_ROOT/runtime/aqcat25_mz73_env.sh"
PHASE=package_and_authorization_boundary
aqcat25_require_remote_path "$PACKAGE_ROOT" "$AUTHORIZATION"
PHASE=host_check
aqcat25_require_mz73
PHASE=job_id
: "${SLURM_JOB_ID:?Slurm job id required}"
PHASE=environment_setup
set -x
aqcat25_setup_mz73_environment "$PROBE_ROOT/job_$SLURM_JOB_ID"
set +x
PHASE=complete
printf 'PASS_NO_MODEL_NO_GPU\n'
