<!-- state-handoff:start current_task -->
# Current Task

## Objective

Use the completed actualML failure-boundary comparison to choose a justified next adsorption-acceleration adjustment without promoting the current model or automatically training.

## Current Evidence Snapshot

- VASP9896148/9896149/9896150 are DONE,normal,EDIFF-converged,with complete finite49-atom forces,exact input/coordinate/POTCAR binding and full local/total magnetic records;SIGMA0.20 NSW0 unchanged.
- User separately authorized one3-structure/two-frozen-model GPU force batch. MZ73 GPU1 actual CUDA execution completed with producer exit0 in6.58s;9returned files verified,no scheduler job emulation.
- Pooled adsorbate vectorRMSE0.269503→0.228471eV/A (15.225% improvement);per-frame before/after/final0.232212→0.177792,0.296110→0.254448,0.276209→0.245445.
- C46 error worsens before0.121081→0.234470 and after0.234895→0.383298eV/A;pooled carbon RMSE worsens0.232396→0.258324,while O/H improve. MovableFe essentially unchanged/slightly worse.
- Final057 frozen2185 fmax0.093003 differs fromDFT0.337048eV/A. Bond projections show local residual errors,but three points do not establish a sole optimizer/basin/path cause or prove the fragmented DFT basin unstable.
- 57scoped tests,compilation/import/Ruff and294-row CSV uniqueness/RMSE recomputation passed. Existing16heldout exclusions and24untrained frames unchanged;no new training,VASP,checkpoint promotion or accepted-energy registration.

## Lifecycle Status

- Phase: `active`

## One Executable Step

Review whether to prepare a targeted carbon/local-Fe force correction request with adsorption replay and isolated validation;any further GPU training requires separate user authorization.

## Submission Boundary

ONE_AUTHORIZED_FORCE_INFERENCE_BATCH_COMPLETE:do not rerun it,train,promote,change old jobs or submit additional VASP under its consumed authority.

## Authoritative Constraint

Execution backend roles and handoffs remain governed by `configs/execution_backends.yaml`.

## Done When

- ActualML failure-boundary exact-structure VASP forces are normal/electronically converged,complete and compatibility/hash-bound.
- Identical-POSCAR originalAQCat25/frozen2185 errors and key-bond force directions are reviewed before choosing targeted adaptation or a basin/geometry strategy.
- Any adopted acceleration is checked against compatible matched VASP steps/time and reviewed final chemistry.

## Constraints

- Preserve the frozen3POSCARs,VASP raw outputs,actual checkpoint hashes,all raw forces and fixedFe0-17 metric exclusion. Force labels are not accepted adsorption minima or reportable energies.
- These3screened related failure points are not independent heldout validation. Keep16observed heldout and24untrained frames isolated;no automatic threshold-based training or model promotion.
- Only work reviews GPU returns;MZ73 is inference/training backend and sunboquan-codex is VASP backend. Preserve credentials and other users' processes.

## Authoritative References

- configs/execution_backends.yaml
- docs/reviews/fe110_06c_boundary_force_comparison_20261019.md
- archive/fe110_adsorption_validation_20261018/authorization_boundary_force_20261019.md
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_06c_force_comparison_20261019_v1/force_comparison_review.json
- calculations/fe110_c2_adsorption_06_10_20261012/adsorption_06c_force_comparison_20261019_v1/per_atom_force_errors.csv
<!-- state-handoff:end current_task -->
