#!/bin/bash
# One candidate inside an explicitly authorized, walltime-bounded direct batch.
set -euo pipefail
: "${AQCAT_PYTHON:?}" "${AQCAT_PILOT_ROOT:?}" "${HANDOFF_ROOT:?}"
: "${AQCAT_RUN_ID:?}" "${MATRIS_CHECKPOINT:?}"
exec "$AQCAT_PYTHON" "$AQCAT_PILOT_ROOT/matris_adsorption_relax.py" \
  --checkpoint "$MATRIS_CHECKPOINT" --handoff "$HANDOFF_ROOT/handoff.json" \
  --output "$HANDOFF_ROOT/output/job_$AQCAT_RUN_ID" --run-id "$AQCAT_RUN_ID"
