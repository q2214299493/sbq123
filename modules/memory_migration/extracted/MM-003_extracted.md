# MM-003 Extracted Notes

## Durable DIMER Lessons

- Early jobs `9429911`, `9430275`, `9430611`, `9430627`, and `9430644` establish distinct SCF, dipole, and no-DIMCAR failure modes.
- Job `9433590` established persistent mode/force oscillation despite no fatal SCF error.
- Job `9434125` established that a simple C/O-only opposite stretch mode can catastrophically diverge.
- Future DIMER starts should come from a chemically valid NEB high-energy image, with mode inspection before submission.

## Durable NEB Lessons

- Image count must be compatible with requested cores; job `9430977` failed at MPI partitioning.
- A TS-like C-O near `2.1 A` is not the D endpoint; job `9434583` encoded the wrong problem.
- Stable SCF settings do not repair a chemically discontinuous path (`9454833`, `9455800`, `9532195`).
- Constrained Fe pre-relaxation can condition the environment, but full displacement transfer can introduce new coordination jumps (`9506942`).
- The largest path error was the wrong periodic branch for O; endpoint-derived minimum displacements corrected it.

## Evidence Qualification

Remote archive directories were confirmed for the key early DIMER failures and several NEB failures. Later path-collapse diagnostics are also supported by local postmortem folders. Exact transient queue states were not migrated.
