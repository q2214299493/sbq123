# Fe(110)06 A/B/C registration and01–05 coadsorption audit

Date:2026-10-21, Asia/Shanghai. User requested all06 A/B/C database records and
an audit for omitted coadsorption states in01–05. No new computation authorized.

## Scope and reviewed plan

The exact append-only plan was applied successfully. Readback confirmed all
59 inserted rows and5 workflow transitions. These represent4 endpoint records,
not59 new adsorption structures. The original rejected interpretation remains
unchanged; exact-repeat application returned the existing receipt without
duplicating any rows.

| Source | Actual final identity | Recorded registry disposition |
|---|---|---|
|06_A,9848799|CO*+C*+H*, arrangementA|Reviewed identity, structure, force and TOTEN; `needs_review` for missing terminal scheduler evidence|
|06_B,9848800|CO*+C*+H*, arrangementB|Separate reviewed state; same scheduler limitation|
|06_C,9848801|Intact C–O–CH*|Preserved as duplicate of the reviewed paired06_C_candidate cluster, not a new independent state|
|03_cfg0_direct_vasp,9839757|CH*+CO*|Separate accepted coadsorption interpretation linked to the rejected original intact-target calculation|

06_A/B were already reclassified to CO+C+H before VASP submission. The VASP
initial/final adsorbate graphs match; do not describe this as a newly observed
VASP-stage dissociation. The distinction between reviewed results and accepted
formal energies is retained explicitly.

## 01–05 audit

All14 source collections were checked against their receipts, including the
actual final structures. Only03_cfg0_direct_vasp changes the intended molecular
identity: C–C separation2.78717Å, final CH*+CO* fragments,295 ionic steps,
movable-atom fmax0.018118895eV/Å, final TOTEN−385.14767079eV. The other13 retain
their requested graph/H placement, including known duplicate endpoints.

The original03 calculation's rejected intact CH–C–O interpretation and review
remain immutable. A child interpretation
`fe110_five_c2_adsorption_20261006_03_cfg0_direct_vasp_CH_CO_reclassified_20261021`
reuses that same job/output evidence. It is **not** a new VASP run or a second
job/cost. Historical recorded LSF DONE, full original-byte local OUTCAR,
electronic/force convergence, chemistry, contacts, compatibility and source
bindings support this reclassification. Before this addition,01–05 already had
8 accepted intact representatives,5 duplicates and1 rejected original target;
the8 include the three separately authorized2026-10-13 scheduler exceptions.
Those task-scoped exceptions are not extended to06.

## 06 evidence boundary

The prior hash-bound full-source extracts and exact restored POSCAR/CONTCAR,
INCAR,KPOINTS,OSZICAR were reused and revalidated through the canonical review.
Both06 coadsorption arrangements are distinct under the earlier surface-aware
comparison.06_C belongs to the existing three-member duplicate cluster.

Current `bjobs -a -w 9848799 9848800 9848801` returned “not found” for all three.
A bounded `bhist` request timed out. Renewed canonical remote metadata reads
timed out at OUTCAR hashing for all three. The failed attempts are preserved;
no unchanged retries, remote job changes or new VASP were performed. Scheduler
state is therefore UNKNOWN, not DONE.06 TOTENs/forces are stored only as
`reviewed`, not `accepted_compatible_final_energy`. Their remote OUTCAR entries
retain the earlier snapshot hash and explicitly note that the renewed remote
hash read did not complete. This is not an electronic/ionic failure finding.

## Registry evidence and verification

Root:
`calculations/fe110_c2_adsorption_06_10_20261012/coadsorption_registration_20261021_v1/`.

- `registry_batch.json`,`registry_plan.json`,`registry_approval.json`: one exact
  reviewed transaction,59 row inserts and5 workflow transitions; no new jobs.
- Plan SHA256:`b12d485bfa373638dbf6bbb38fa856227c880fd06a325c937597d9ad8aba4bdf`.
- Applied rows:1 child interpretation,3 UNKNOWN scheduler observations,
  35 file references,12 results,4 scientific reviews,4 compatibility bindings.
  These are4 endpoint records, **not59 adsorption structures**.
- `old01_05_audit.json`,`scientific_reviews/`: exact chemical identities,
  initial/final projection/contact/angle evidence, source hashes and eligibility.
- `preparation_source_used.py`: exact source bytes bound by the preparation
  summary; later code extracts a helper without altering the saved batch.
- `collection_failures.json`,`read_attempt_failures.json`: bounded failed
  retrieval/preparation attempts and the actual resolution.
- Scoped tests:142 passed; after the helper extraction,3 direct chemistry
  tests passed again. Scoped Ruff and Python compilation passed.
- `registry_receipt.json`,`post_apply_verification.json`,
  `idempotency_receipt.json`: complete applied-row readback, original rejection
  preserved, `quick_check=ok`, empty foreign-key check and exact retry confirmed.

The first readback attempt compared a new calculation's creation-time
`registered` projection with its correctly transitioned `accepted` state.
Only the verifier was corrected to compare the final planned projection;
the saved successful transaction was not resubmitted or rewritten.

No adsorption-energy reference tuple, thermal/free-energy correction, Excel
publication or model promotion is inferred. Database acceptance and thesis
table promotion remain different stages. Registration adapters use the existing
canonical `registry-write` and source-bound scientific owner; they are under
`archive/fe110_coads_registry_20261021/`.

Repository-state projection sync still reports the pre-existing classification
conflict at `sbq_catalyst_agent_workflow.egg-info/PKG-INFO`. This is not a failed
database transaction; the registry receipt/readback above succeeded. No unrelated
classification repair or legacy dirty-database publication was attempted.
