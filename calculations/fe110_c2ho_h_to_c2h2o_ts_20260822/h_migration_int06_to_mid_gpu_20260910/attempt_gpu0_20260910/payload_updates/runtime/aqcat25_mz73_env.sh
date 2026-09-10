#!/bin/bash

# BEGIN GPU BOOTSTRAP GUARD (mirrored from aqcat25_mz73_env.sh)
# This dependency-free guard must exist even when the shared helper is missing.
gpu_bootstrap_failure() {
  local code=$? directory record
  [ "$code" -ne 0 ] || return 0
  record=$(printf '{"document_kind":"gpu_wrapper_execution_failure","status":"failed","phase":"bootstrap","exit_code":%d,"evidence_class":"producer_process_only_not_scheduler_accounting"}' "$code")
  printf '%s\n' "$record" >&2
  directory=$(pwd -P)
  case "$directory" in
    /home/sbq/sbq|/home/sbq/sbq/*)
      (umask 077; set -C; printf '%s\n' "$record" > "$directory/producer_exit_record.failure.bootstrap.$$.json") || : ;;
  esac
}
aqcat25_install_bootstrap_guard() {
  trap gpu_bootstrap_failure EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP
}
# END GPU BOOTSTRAP GUARD

# Single owner for the MZ73 runtime contract.  GPU wrappers source this file
# instead of repeating host, Python, and cache setup.
AQCAT_MZ73_HOST=${AQCAT_MZ73_HOST:-MZ73}

aqcat25_require_mz73() {
  local observed_host
  observed_host=$(hostname)
  if [[ "$observed_host" != "$AQCAT_MZ73_HOST" ]]; then
    echo "AQCat25 GPU jobs must run on $AQCAT_MZ73_HOST (observed $observed_host)" >&2
    return 2
  fi
}

aqcat25_setup_mz73_environment() {
  AQCAT_ROOT=${AQCAT_ROOT:-/home/sbq/sbq/aqcat25}
  AQCAT_PYTHON=${AQCAT_PYTHON:-/home/sbq/sbq/ml_ts_acceleration/venv/bin/python}
  AQCAT_PILOT_ROOT=${AQCAT_PILOT_ROOT:-/home/sbq/sbq/aqcat25_ts_pilot}
  export AQCAT_ROOT AQCAT_PYTHON AQCAT_PILOT_ROOT AQCAT_MZ73_HOST
  export PYTHONPATH="$AQCAT_PILOT_ROOT:$AQCAT_ROOT/python_pkgs:$AQCAT_ROOT/vendor${PYTHONPATH:+:$PYTHONPATH}"
  export XDG_CACHE_HOME=${XDG_CACHE_HOME:-$AQCAT_ROOT/cache/xdg}
  export TORCH_HOME=${TORCH_HOME:-$AQCAT_ROOT/cache/torch}
  export HF_HOME=${HF_HOME:-$AQCAT_ROOT/cache/huggingface}
  export TMPDIR=${TMPDIR:-$AQCAT_ROOT/tmp}
  export WITH_PYG_LIB=0
  export TORCH_SPARSE_USE_PYG_LIB=0
  export TORCH_SCATTER_USE_PYG_LIB=0
  export WANDB_MODE=disabled
  export PYTORCH_CUDA_ALLOC_CONF=${PYTORCH_CUDA_ALLOC_CONF:-expandable_segments:True}
  # A venv interpreter may link to system Python. It is executed, never a write
  # target; retain canonical containment for its parent and every writable path.
  aqcat25_require_remote_path "$AQCAT_ROOT" "$(dirname -- "$AQCAT_PYTHON")" "$AQCAT_PILOT_ROOT" \
    "$XDG_CACHE_HOME" "$TORCH_HOME" "$HF_HOME" "$TMPDIR" "$@" || return 2
  test -x "$AQCAT_PYTHON" || return 2
  mkdir -p "$XDG_CACHE_HOME" "$TORCH_HOME" "$HF_HOME" "$TMPDIR" "$@"
}


# Canonical containment is shared by environment setup, wrappers and reporting.
aqcat25_require_remote_path() {
  local path canonical boundary
  boundary=$(realpath -e -- /home/sbq/sbq) || return 2
  [ "$boundary" = /home/sbq/sbq ] || return 2
  for path in "$@"; do
    case "$path" in /home/sbq/sbq|/home/sbq/sbq/*) ;; *) return 2 ;; esac
    canonical=$(realpath -m -- "$path") || return 2
    case "$canonical" in "$boundary"|"$boundary"/*) ;; *)
      echo "path escapes /home/sbq/sbq: $path" >&2; return 2 ;;
    esac
  done
}

# Write-once emergency evidence uses Bash, not the possibly broken ML Python.
# Normal producer receipts remain owned by their existing writers.
aqcat25_record_wrapper_failure() {
  local code=$1 record job host target directory suffix TZ=UTC
  export TZ
  job=${SLURM_JOB_ID:-unknown}
  [[ "$job" =~ ^[0-9]+$ ]] || job=unknown
  host=${HOSTNAME:-unknown}
  [[ "$host" =~ ^[A-Za-z0-9_.-]+$ ]] || host=unknown
  suffix="producer_exit_record.failure.$job.$$.json"
  printf -v record '{"document_kind":"gpu_wrapper_execution_failure","gpu_job_id":"%s","hostname":"%s","status":"failed","exit_code":%d,"phase":"wrapper","finished_utc":"%(%Y-%m-%dT%H:%M:%SZ)T","evidence_class":"producer_process_only_not_scheduler_accounting"}' "$job" "$host" "$code" -1
  printf '%s\n' "$record" >&2
  # Prefer the contract's receipt path if it does not exist. A unique sibling
  # preserves previous evidence when the normal writer already produced a file.
  for target in "${EXIT_RECORD:-}" "${OUTPUT_ROOT:-${OUTPUT:-}}/$suffix" "${GPU_EXECUTION_FALLBACK_DIR:-}/$suffix"; do
    [ -n "$target" ] || continue
    aqcat25_require_remote_path "$target" || continue
    directory=${target%/*}
    if [ ! -d "$directory" ]; then
      mkdir -p -- "$directory" || continue
    fi
    aqcat25_require_remote_path "$target" || continue
    if (umask 077; set -C; printf '%s\n' "$record" > "$target"); then
      echo "GPU wrapper failure record: $target" >&2
      return 0
    fi
  done
  # If storage is unavailable, the JSON above remains in the Slurm stderr log.
  # No record-file claim or success is made; missing file evidence stays UNKNOWN.
  return 1
}

aqcat25_finish_execution() {
  local code=$1
  trap - EXIT
  set +e
  if [ "$code" -ne 0 ]; then
    aqcat25_record_wrapper_failure "$code"
  fi
  exit "$code"
}

aqcat25_begin_execution() {
  GPU_EXECUTION_FALLBACK_DIR=$(pwd -P)
  trap 'aqcat25_finish_execution "$?"' EXIT
  : "${SLURM_JOB_ID:?SLURM_JOB_ID is required}"
  [[ "$SLURM_JOB_ID" =~ ^[0-9]+$ ]] || return 2
  aqcat25_require_mz73 || return 2
}


aqcat25_require_sha256() {
  [[ "$1" =~ ^[[:xdigit:]]{64}$ ]] || { echo "Invalid SHA-256 digest" >&2; return 2; }
}
