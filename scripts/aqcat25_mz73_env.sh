#!/bin/bash

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
  mkdir -p "$XDG_CACHE_HOME" "$TORCH_HOME" "$HF_HOME" "$TMPDIR" "$@"
}
