# Fe(110) C2 registration and GPU handoff — 2026-10-13

## User authority and scope

User request: “都录入吧 然后把那15个也提交gpu”. This follows the explicit
explanation that the three completed jobs lack original scheduler DONE records.
The accepted exception is limited to 02_extra2/9842106, 04_cfg2/9839755 and
05_cfg1/9839754. Their scheduler states remain UNKNOWN. No scientific check,
DFT parameter, source output, duplicate rule or global production policy changed.

## Completed registration

Canonical append-only batch `fe110_c2_three_scheduler_exceptions_20261013`
inserted 15 metadata/result rows and three workflow transitions, not 15 new
adsorption structures. Existing calculations, jobs and source-file IDs were reused.
Each accepted final TOTEN and reviewed movable force binds original VASP sources,
compatibility and a new task-scoped review. No adsorption energy was inferred.

| Candidate | Job | Final TOTEN (eV) | Movable fmax (eV/Å) |
|---|---:|---:|---:|
| 02_extra2 | 9842106 | -380.90590972 | 0.019586 |
| 04_cfg2 | 9839755 | -384.12661226 | 0.013766 |
| 05_cfg1 | 9839754 | -383.78675386 | 0.019900 |

Database readback: eight accepted, five duplicate, one rejected original target;
quick_check=ok, no foreign-key violations. Eight geometric representatives are
not proof of eight separate basins or global minima. Earlier reviews remain immutable.
Receipts are under
`calculations/fe110_five_c2_adsorption_20261006/final_review_20261012/registration_exception_20261013/`.

## GPU package and current blocker

The reviewed `candidates_v2` fifteen structures (06–10, A/B/C each) were frozen
into `calculations/fe110_c2_adsorption_06_10_20261012/gpu_batch_v1/` and uploaded
to `/home/sbq/sbq/aqcat25_ts_pilot/fe110_c2_06_10_20261013_gpu_v1` on MZ73.
Eleven CARE poses plus four constructed hypotheses remain exploratory candidates,
not fifteen literature-proven stable adsorption states. Soft warnings for
06_A, 07_A and 09_B are retained; no extra bond restraint was introduced.

Model: original AQCat25 demo_single, checkpoint SHA256
`e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50`.
Each relaxation is bounded to 80 LBFGS steps, fmax=0.10 eV/Å; one GPU,
four CPU cores, 32 GiB RAM and two-hour batch limit, matching the earlier
pre-relaxation workflow. No fine-tuned checkpoint promotion or speedup claim.

Local and remote handoff/hash/ASE structure preflight passed for all 15 without
running a model. Remote bash syntax check passed. GPU1 had 15 MiB used out of
24564 MiB; GPU0/2/3 were near capacity at the initial observation. This is an
observation, not a reservation or guarantee of allocation.

MZ73 Slurm controller configuration points to MZ73:6817. `ps -C slurmctld`
returned no process; `systemctl is-active slurmctld slurmd` returned failed/failed.
Queue query could not contact the controller; bounded `sbatch --test-only`
timed out. No real sbatch submission, scheduler job ID, model execution,
service restart or direct launch occurred. Preserve the package and restore
Slurm availability through the administrator before submitting; first recheck
its hashes, absence of previous output/submission and live scheduler resources.

## Validation

- Python syntax compilation passed for task preparation and GPU preflight.
- Fifteen exact graph/H-position, slab/cell/fixed-layer and geometry checks passed.
- Local and remote no-model preflight: PASS, 15 candidates.
- Scoped completion/registry/governance tests: 82 passed.
- Canonical registry plan/apply and database readback passed.
- GPU optimization, final structures and acceleration benefit remain untested.

The unrelated existing global state-sync failure at
`sbq_catalyst_agent_workflow.egg-info/PKG-INFO` was not repaired by this task.
