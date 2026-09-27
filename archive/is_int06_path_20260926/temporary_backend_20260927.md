# Temporary VASP backend handoff

User request: temporarily submit the reviewed GPU1802 coarse NEB to
10.68.0.103:22, nsgkx_cdj1. Separate SSH alias `sunboquan-cdj1-temp` is configured
as an alternate scoped to `h_is_a_int06_gpu1802_neb_20260926`; the original
`sunboquan-codex` identity and default backend are unchanged.

Remote login, ycn03/LSF, existing VTST executable and Intel environment passed.
Existing Fe/C/O and H datasets were combined remotely without downloading or
publishing POTCAR. The result matches the original Fe/C/O/H SHA256 exactly.
The same 108-rank, nine-interior input bundle has a fresh target-bound gate.

Canonicalized HOME comparison accepts the site's mapped home directory while
retaining all sbq/descendant symlink guards. 51 related backend/submission/gate
tests passed; targeted Python compilation and Ruff passed.

Submission did not reach bsub. Noninteractive login stdout contaminated SCP,
which reported `Received message too long 220204320`. Both reservations remain
immutable; the remote target directory is absent. The read-only scheduler
checkpoint shows only six September 15 jobs, not this September 27 attempt.
Canonical status remains `UNKNOWN_NEEDS_RECONCILIATION`, not SUBMITTED.

Next: operator reviews this evidence and explicitly confirms no matching job
before authorizing a new attempt with banner-safe transfer. Do not delete the
existing markers, silently retry, modify remote login startup, or change
scientific parameters. No VASP/NEB scientific result is established here.
