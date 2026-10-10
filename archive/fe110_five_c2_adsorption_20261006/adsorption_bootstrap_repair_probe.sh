#!/bin/bash
#SBATCH --job-name=c2-ads-bootstrap-repair
#SBATCH --partition=normal
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:01:00
#SBATCH --no-requeue
set -euo pipefail
PROBE_ROOT=/home/sbq/sbq/adsorption_c2_finetune_20261010_v3/bootstrap_probe_v2
finish() {
  code=$?
  trap - EXIT
  printf 'REPAIR_PROBE_EXIT code=%d\n' "$code"
  (umask 077; set -C; printf '{"document_kind":"no_model_bootstrap_repair_exit","job_id":"%s","exit_code":%d,"model_run":false,"GPU_requested":false}\n' \
    "$SLURM_JOB_ID" "$code" > "$PROBE_ROOT/exit_$SLURM_JOB_ID.json") || :
  exit "$code"
}
trap finish EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
printf 'INHERITED_TMPDIR=%q\n' "${TMPDIR-UNSET}"
# Execute the actual repaired wrapper only up to environment setup. Tests bind
# this prefix to contain no Python invocation, checkpoint load or model run.
awk '/^EXIT_RECORD=/{exit} {print}' "$PROBE_ROOT/repaired_wrapper.sh" | /bin/bash -x -s
test -d "$PACKAGE_ROOT/output/job_$SLURM_JOB_ID/tmp"
printf 'PASS_REPAIRED_BOOTSTRAP_NO_MODEL_NO_GPU\n'
