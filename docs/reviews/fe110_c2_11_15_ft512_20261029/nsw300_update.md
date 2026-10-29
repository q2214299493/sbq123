# User-requested NSW300 update — 2026-10-29

All15 current task inputs are NSW300. Physical settings other than NSW are unchanged;
EDIFFG=-0.02eV/A,32ranks,Fe45/cell/fixedmask/PBE/POTCAR/KPOINTS/spin and magnetic seeds remain the approved branch.
The global80-step pre-screen policy is unchanged;this batch now uses routine_production.

Live verification: `2026-10-29T07:23:43.403287+00:00`. All90 core input hashes matched on the VASP host.
Running11_C/12_A OUTCAR headers independently show NSW300;other13 are PEND at this checkpoint.

| Structure | Current LSF ID | State | Handling |
|---|---:|---|---|
| 11_A | 9927793 | PEND | CONTCAR continuation;parent9927512 at8steps |
| 11_B | 9927794 | PEND | CONTCAR continuation;parent9927513 at4steps |
| 11_C | 9927514 | RUN | original job ID retained |
| 12_A | 9927515 | RUN | original job ID retained |
| 12_B | 9927516 | PEND | original job ID retained |
| 12_C | 9927517 | PEND | original job ID retained |
| 13_A | 9927519 | PEND | original job ID retained |
| 13_B | 9927521 | PEND | original job ID retained |
| 13_C | 9927522 | PEND | original job ID retained |
| 14_A | 9927523 | PEND | original job ID retained |
| 14_B | 9927524 | PEND | original job ID retained |
| 14_C | 9927525 | PEND | original job ID retained |
| 15_A | 9927526 | PEND | original job ID retained |
| 15_B | 9927527 | PEND | original job ID retained |
| 15_C | 9927528 | PEND | original job ID retained |

13PEND jobs were held with bstop,PSUSP verified,before changing any input.
Only INCAR NSW and candidate stage/provenance metadata changed. Original INCAR
and candidate manifests remain as .before_nsw300_20261029 backups,with old hashes verified.
All new hashes were checked before bresume;later readback proved all13 resumed.

11_A/11_B received current hash-bound STOP_JOB gates,then STOPCAR LSTOP.
They terminated normally at8/4completedionicsteps;neither reached the force-accuracy marker.
Reviewed CONTCAR order/cell/fixedFe/targetC2H3graph/contacts pass. Only the saved geometry
was reused;wavefunction and optimizer history were not imported. New300-step continuations
9927793/9927794 passed native adsorption preflight,INCAR custodian and current bound SUBMIT_VASP gates.
All original outputs and receipts remain unchanged. No old job was resubmitted twice.

Actual execution uses the existing adsorption gate in C:/Users/86177/Desktop/work.
The source-release base has an older TS-only gate;its denial is preserved and was not bypassed.
The adapter delegates to an identical reviewed copy in current work for execution.
Owner source snapshots and hashes are preserved for audit,not new scientific authority.
The release scheduler schema now explicitly accepts adsorption_relaxation rather than mislabelling it as NEB.

Recovery records are retained:initial legacy-schema/gate rejection;CRLF text re-encoding
rejected before any remote write;after exact-byte transfer,bresume succeeded but the immediate
queue read still showed PSUSP. Reconciliation confirmed13exact new bundles/old backups and
subsequent RUN/PEND states. No unchanged mutation was repeated after a possible write.
STOPCAR disappeared when VASP processed the graceful-stop request;normal terminal evidence was collected.

Validation:106scoped release tests and11current-work adsorption tests pass;Python syntax and Ruff pass.
Registry:209append-only metadata inserts,4reviewed workflow projections,213readbacks,zero scientific results.
The two stopped parents are needs_review;their final energies are not accepted results.

NSW300 remains a limit,not a convergence guarantee. Final DFT force,SCF,magnetism,chemical/site
stability and compatible energies remain pending. No automatic continuation beyond this request.
Evidence:nsw300_evidence.zip;canonical live working directory:
calculations/fe110_c2_adsorption_11_15_20261020/ft512_gpu_20261029_v1/nsw300_update_20261029_v1/.

State projection did not complete:existing PKG-INFO classification mismatch. No unrelated metadata repair was performed.
