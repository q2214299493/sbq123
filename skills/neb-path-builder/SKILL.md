---
name: neb-path-builder
description: Build evidence-guided VASP VTST NEB paths with chemical waypoints, endpoint consistency, geometry tables, dist.pl, nebmovie.pl 0, and review exports.
---

# NEB Path Builder

Use `modules/transition_state_search/README.md` as the canonical procedure.

## Evidence Gate

- Start from verified local endpoints and accepted records from `catalysis-data-retrieval` when external evidence is needed.
- Do not run an independent literature or web search.
- Treat retrieved structures and paths as candidates, not hard constraints.

## Hard Rules

- Do not use pure endpoint interpolation for chemically complex bond breaking.
- Preserve atom order, cell compatibility, and Selective Dynamics flags.
- Do not use a TS-like C-O distance near `2.1 A` as a dissociated endpoint.
- Build chemical waypoints, then smooth only between neighboring compatible states.
- Before submission, run `dist.pl`, generate geometry/path-continuity tables, run `nebmovie.pl 0`, and obtain review approval.
- After completion or stop, run `nebmovie.pl 1` before barrier or TS interpretation.

This skill constructs and checks paths; it does not retrieve external evidence, submit jobs automatically, or accept a TS.
