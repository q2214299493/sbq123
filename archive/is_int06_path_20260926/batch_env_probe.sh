#!/bin/bash
# No model, checkpoint, GPU allocation or input mutation. Only path variables.
set -eu
for name in TMPDIR XDG_CACHE_HOME TORCH_HOME HF_HOME AQCAT_ROOT AQCAT_PYTHON AQCAT_MZ73_HOST; do
  printf '%s=%s\n' "$name" "${!name-UNSET}"
done
