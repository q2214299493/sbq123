# CH + CO formal TS acceptance — 2026-11-16 CST

## Accepted result

Existing Dimer9998592 and VFA2260 pass formal TS acceptance for
CH* + CO* -> CH-C-O*. Owner VFA analysis is VALIDATED/Grade A;
the resumable scientific pipeline reports TS_ACCEPTED. The current hash-bound
execution decision is VALIDATED_TS and permits APPROVE_TS_CANDIDATE.

The registered validation ID is
`fe110_ch_co_dimer9998592_vfa2260_grade_a_20261115`.
The evidence directory retains its initial UTC-date suffix:
`calculations/fe110_ch_co_to_chco_ts_20261109/ts_acceptance_20261115_v1/`.

## Scientific review

- Dimer:normal completion,electronic convergence,max atomic force0.015198eV/A
  against0.02eV/A,and negative curvature-5.751eV/A2. Initial/final modes,
  geometry,contract and source hashes remain reviewed and current.
- Complete DIMCAR record48 retains Force0.06316/Torque0.20789 warnings.
  Terminal49 is force-only;missing curvature/torque were not fabricated.
  The new formal review accepts the exact residuals for TS validation based on
  hard convergence and clear completed target-mode evidence. It does not claim
  that the soft numerical targets passed. The old frequency-only approval is
  unchanged and separately referenced by hash.
- VFA:normal completion,12 modes,exactly one imaginary mode12 at318.644011cm^-1.
  The actual quantitative and visual review identifies C45–C46 opening/closing,
  not primarily C–O or C–H rupture. Same-active-set absolute cosine with the
  final Dimer direction is0.934.
- The local partial Hessian covers C45/C46/O47/H48 (zero-based). Frequency
  geometry is exactly the calculated structure;all reaction atoms are active.
  Scope review was refreshed in a new review copy,not by editing submitted data.
  Original source files and all11 frequency inventory hashes were checked.

Correction to the preceding diagnostic summary:unset numerical frequency
thresholds are not a blanket blocker. The existing protocol permits Grade A
for a complete Dimer result with exactly one explicitly reviewed target
imaginary mode and accepted geometry/source evidence. That reviewed-single-mode
branch was used;no cutoff or scientific configuration was changed.
Downhill connectivity remains optional and was not performed or fabricated.

## Registration and validation

- Reviewed registry plan:26 metadata inserts (24 files,one terminal job
  observation,one formal review) and one frequency-workflow transition to done.
  This is distinct from the one accepted TS-validation record.
- Scientific validation was written only by the existing gated TS owner.
  Readback verifies the exact metadata,validation identity/Grade A,workflow
  status,evidence-file hashes and preserved old diagnostic approval.
  SQLite quick_check and foreign_key_check pass.
- A gate adapter omission was first reproduced by a failing regression:
  it did not pass the handoff-bound Dimer soft review into the owning pipeline.
  The minimal fix forwards that path (including relative-path resolution).
  The owner still rejects diagnostic-only,missing or stale reviews;no scientific
  predicate or priority rule was relaxed.108 targeted regressions,Python
  compilation and Ruff pass. Published source copies are byte-identical.

## Limits and next step

The database kinetic_eligible flag is TS-validation eligibility,not proof of
available free-energy or rate-constant inputs. This is a four-atom local Hessian,
not a full-slab vibrational proof. The approved VFA SIGMA0.10 profile supplies
frequency evidence only;its energy is not part of the SIGMA0.20 final-TOTEN chain.

No new scientific job,energy/barrier record,thermal correction,Excel numerical
promotion,training or transferable success template was created. Barrier plus
method-template registration still require their separate compatible-energy
and learning gates. Next:review compatible accepted IS/TS/FS final OUTCAR TOTEN
under fe110_converged_toten_sigma0p20_v1 before barrier reporting.

No RSI/model invocation was repeated for this procedural acceptance/registration;
the earlier blocked RSI opinion remains unused. The conclusion follows current
scientific-owner reanalysis of preserved VASP data and reviewed mode evidence.
