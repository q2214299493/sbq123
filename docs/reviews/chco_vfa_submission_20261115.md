# CH + CO local frequency submission —2026-11-15

## Outcome and authorization

One32MPI/32pernode local partial-Hessian job was submitted through the canonical
START_VFA executor on sunboquan-codex:LSF **2260**. First native observation:
PEND at2026-11-15T06:49:23Z. No claim that VASP or displacement evaluation had
started follows from PEND.

Remote:`~/sbq/Fe110/ts/ch_co_to_chco_20261110/vfa_dimer9998592_20261115_v1`.
Local:`calculations/fe110_ch_co_to_chco_ts_20261109/vfa_dimer9998592_20261115_v1/`.

User requested frequency submission,then—after disclosure of the exact DIMCAR
residuals—conditionally accepted them if normal convergence and geometry checks
passed. Those checks passed. The bound review is **allow_frequency_handoff**,
not accept_for_ts_validation. Its gate reports frequency_handoff_allowed=true
and ts_validation_eligible=false. No formal TS/barrier was accepted.

## Actual completed Dimer evidence

Source:Dimer9998592,from ordinary NEB9994246 image05 and reviewed04/06 tangent.
Native scheduler DONE;16remote files/65,316,812bytes collected,all hashes checked,
all submitted input hashes unchanged. Raw outputs and original submission
records were preserved in an independent completion snapshot.

- 49translation records;last full Force/Torque/curvature row is48. Terminal49
 has Force0.04239 but dashes for Torque/curvature;it was retained,not filled in.
- VASP maximum atomic force0.015198eV/A meets0.02eV/A. Last electronic step15,
 EDIFF1e-7 termination confirmed;normal OUTCAR ending,no fatal parser markers.
- Last complete DIMCAR row:Force0.06316,Torque0.20789,curvature-5.751eV/A2.
 These Force/Torque values miss their soft targets;they were not called passed.
- Final CC1.73996433A,CO1.22780417A,CH1.10079907A;CH and CO remain intact.
 No evident collision or fixed-layer drift. Bottom18Fe maximum motion
 7.61e-14A;cell/order/constraints match the source.
- Final49-row NEWMODECAR is finite,normalized,and zero on fixed atoms;88.828%
 squared amplitude lies on C45/C46/O47/H48. Target CC directional derivative
 is-1.21426A per unit mode. Actual top/side arrows were visually reviewed.
- Last complete49-atom force/coordinate table is finite;CONTCAR correspondence
 error7.8752e-6A is within printed-output precision.

This establishes technical Dimer evidence and a diagnostic frequency candidate,
not a first-order-saddle frequency conclusion. The parent scalar-CC sampling
warning is retained;no general threshold or scientific protocol changed.

## Frequency scope and numerical branch

Active zero-based atoms:**45,46,47,48** = C,C,O,H. All contract reaction atoms
are active. All45Fe atoms are fixed for this local Hessian;the saddle coordinates,
cell and atom order are unchanged. The source/frequency geometry identity and
shared owner scope checks passed. Local substrate coupling outside this active
set is not claimed resolved by a full Hessian.

Inputs come from the current repository VFA builder/profile:
IBRION5,NFREE2,POTIM0.015A,NSW1,EDIFF1e-7,PBE,ENCUT400eV,Gamma5x5x1,
ISPIN2,ALGO Fast,ISMEAR1,SIGMA0.10eV. This is the existing frequency template,
not the SIGMA0.20eV Dimer final-energy branch. The distinction was disclosed
before submission. No VFA energy enters the compatible electronic-barrier
chain,and no ZPE/thermal/free-energy correction is being reported.

Fresh remote runtime,target/reservation and POTCAR hash checks passed. No
unfinished account job was reported at preflight. Licensed POTCAR contents
were not downloaded;the canonical executor verified the remote copy.
Input bundle SHA256:
`d81c7174cc91d8cee86881df842afc2f7f1a007ea4cf98e47c21c7e26b4d63df`.

No pilot,NEB,Dimer restart,GPU,training,connectivity or extra frequency job.

## Verification and registration

Canonical Dimer evidence/mode review,conditional residual approval,partial-Hessian
handoff,INCAR custodian and VFA submission preflight passed. START_VFA was the
only allowed action. Current gate validation,all16raw hashes,geometry identity
and scope checks were rechecked after submission.73related tests passed across
TS validation,handoff,execution gate,submission and VASP inputs. Scoped Ruff and
syntax checks passed;one unused registration import was removed after its
lint finding. The successful database transaction was not repeated.

Canonical registration inserted48metadata rows:1calculation,1job,2status
observations and44file records,plus1parent submitted->done workflow change.
Exact-plan approval,readback,quick_check and foreign-key checks passed.
These are provenance rows,not48structures or accepted results. Zero frequency,
TS or barrier result rows were inserted. Licensed VFA POTCAR is remote-only.

## Next and remaining boundary

Inspect VFA2260 normal/electronic/displacement completion,all frequencies and
eigenvectors,then assign any principal imaginary mode to the target C-C event.
No imaginary frequency is known yet. A complete single target mode still
requires the owning acceptance review;this frequency-only residual decision
must not silently become formal TS approval. No automatic retry,expanded
Hessian,barrier report,thermal correction or another job is authorized.
