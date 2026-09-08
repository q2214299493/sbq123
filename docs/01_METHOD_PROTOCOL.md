# Method Protocol

## 1. Resume a Task

Use the minimal startup sequence in `AGENTS.md`. Verify only the live sources required by the current task.

## 2. Structure and Path Checks

The project-wide external-data gate is `modules/catalysis_data_retrieval/`; the
canonical fingerprint, template retrieval, NEB/CI-NEB, DIMER refinement, and
learning workflow is `modules/transition_state_search/`. For any Fe-surface CO
step, preserve `Fe C O` order and Selective Dynamics, report C-O/C-Fe/O-Fe
geometry, and never treat a C-O distance near `2.05 A` as the dissociated
endpoint.

Before planning a new adsorption calculation, normalize the target and search
the approved catalysis-data whitelist with BM25 plus semantic ranking. If a
usable matching adsorption motif exists, stop external retrieval and do not run
literature search. Only a recorded `NO_WHITELIST_MATCH` opens the controlled
authoritative-journal fallback owned by `catalysis-data-retrieval`.

The fallback accepts peer-reviewed primary research from authoritative
chemistry, materials, and catalysis journals, prioritizing Nature-family,
JACS/ACS Catalysis and other directly relevant ACS journals, Science-family,
Angewandte Chemie, Chemical Science, and Journal of Catalysis without treating
that example list as exhaustive. Verify DOI and publisher provenance, exact
surface/facet and adsorbate identity, reported stable geometry, and direct
stability evidence. Non-exact facets and review speculation are not build-ready
evidence. Candidate count equals the number of unique stable motifs supported
by the accepted evidence: use two when two are supported and four only when
four are supported. Never pad the calculation set to the four geometric site
classes. Existing accepted local structures may still be reused directly.

External adsorption evidence is a compute-saving structure prior only. Use it
to select and rank motifs and to initialize reviewed sites, binding atoms, bond
lengths, bond angles, surface heights, and orientations. Reported literature or
database energies may validate relative ordering but must never be imported as
local adsorption energies, entered in the registry or Excel, or compared
numerically with the active branch. Local relaxation, convergence, geometry
review, and compatible hash-bound final-energy evidence remain mandatory.

For Fe(110), `top`, `short_bridge`, `long_bridge`, and true three-coordinate
`hollow` are a geometric dictionary generated only through
`scripts/adsorption/build_fe110_adsorption.py`; they are never an automatic
four-calculation list. Site geometry depends exclusively on the clean relaxed
slab's highest-z Fe layer: the shortest top-layer Fe-Fe distance class defines
short bridge, the next distinct class defines long bridge, and a valid hollow
is the centroid of an adjacent three-Fe triangle and must not coincide with any
Fe-Fe midpoint. Adsorbate-specific behavior belongs only in evidence-gated
motif plans and reviewed structure templates.

After the evidence and initial-structure gates pass, AQCat25 on `BUCT(sbq)` may
pre-relax and rank the accepted adsorption candidates. It is a compute-saving
screen only: predicted energy/force values cannot enter adsorption-energy
tables, and one AQCat result cannot remove an evidence-required motif, prove a
final site or global minimum, or replace compatible VASP relaxation/final
statics. Each GPU result must return through `work` with the source plan,
structure, compatibility, model/checkpoint, unit, optimizer, and domain-status
bindings defined in `configs/execution_backends.yaml` before a VASP package is
prepared for `sunboquan-codex`.

## 3. Unified Fe Production Parameters

Validated scope: alpha-Fe conventional bcc and the corrected true Fe(110) 3x3
clean-slab family.

- Dataset-wide locked settings: `GGA=PE` (PBE), the same approved PAW-PBE POTCAR family, and `ENCUT=400 eV`. Apply these to bulk, clean slabs, adsorbed slabs, endpoints, transition-state calculations, and isolated molecular references used in adsorption or reaction energies.
- Spin policy: use `ISPIN=2` with species-resolved `MAGMOM` for Fe-containing magnetic systems. Gas-phase closed-shell CO is non-spin-polarized: use `ISPIN=1` and omit `MAGMOM`.
- Final-energy convention: use a validated and explicitly documented convention
  for every reported energy difference. Keep `EDIFF`, `EDIFFG`, `ISMEAR`, and
  `SIGMA` identical within the same system group and workflow stage wherever
  scientifically valid. Metallic slabs and isolated molecular references may
  use different occupation settings when physically required, but their final
  energies must follow the convergence and compatibility rules below. Metals
  and oxides may use separately converged smearing, magnetic, and DFT+U
  branches. Never mix undocumented, unconverged, or incompatible branches in
  one reported energy difference.
- Relaxed production states use `EDIFF=1E-5` and `EDIFFG=-0.02 eV/A`. A converged, geometry-valid Fe(110) production relaxation may provide a formal surface-state energy under the active convention below. The `-0.05 eV/A` screening/ordinary-NEB branch remains exploratory.
- The active five-layer Fe(110) final-energy convention is the final `OUTCAR` `TOTEN` from the compatible `ISMEAR=1`, `SIGMA=0.20 eV` production branch (`fe110_converged_toten_sigma0p20_v1`). A separate single-point calculation is not required. IS/TS/FS barriers require compatible accepted endpoint relaxations and a technically accepted saddle-search result under this same convention. Existing `SIGMA=0.10 eV` matched statics remain optional convergence/provenance records and cannot be mixed into this active energy chain. Alpha-Fe bulk tetrahedron statics remain separate bulk-reference calculations.
- Every final-barrier compatibility fingerprint must directly include
  `ISMEAR`, `SIGMA`, the exact zero-based fixed-atom index mask, `LDIPOL`,
  numeric vacuum thickness, and the final-energy convention identifier in
  addition to the material/XC/POTCAR/ENCUT/k-mesh/magnetic/slab fields.
  Legacy incomplete fingerprints may still be read for path provenance but
  are ineligible for final barrier registration.
- For the same surface family and coverage branch, keep the lateral cell, slab thickness, vacuum thickness, fixed-layer count/rule, dipole policy, and slab k-mesh identical. Different dimensionalities may use different numerical k meshes only when reciprocal-space density remains convergence-backed; isolated references use the same cell and Gamma-only protocol across comparisons.
- Common Fe initialization: `MAGMOM=2.2 mu_B/Fe atom`; generate all species segments from POSCAR order and counts.
- Evidence-bound exception: the Fe(110) CO-dissociation ordinary-NEB branch
  `fe110_co_dissociation_highspin_seed_v1` uses `MAGMOM=2.4 mu_B/Fe atom`
  only as its initial magnetic seed. Exact-geometry diagnostic job `9639279`
  established the lower-energy high-spin branch; this exception does not
  change XC, POTCAR, ENCUT, k-mesh, smearing, slab, constraints, or the
  active compatible-final-energy gate.
- `MAGNETIC_CONTINUITY_RULE`: an adjacent-image total-magnetization difference
  above `2.0 mu_B` is a `SOFT_WARNING`. It triggers magnetic-state continuity
  review but cannot by itself stop a job, block ordinary no-climb NEB, or prove
  a magnetic-state switch. Any stronger conclusion requires supporting SCF,
  local-moment, energy, and structure evidence.
- NEB diagnostic severity policy: one `NELM` exhaustion, early/nonpersistent
  high force, a transient internal energy minimum, a single-coordinate
  backtrack, large mapped endpoint motion, surface penetration/desorption
  heuristics, and downhill endpoint-tolerance misses are review evidence, not
  independent stop or rejection authority. Hard failure requires verified
  source files plus data corruption/incompatibility, a fatal VASP error,
  consecutively repeated electronic exhaustion, an unphysical collision, or
  independently persistent path-discontinuity evidence.
- The default NEB high-force policy treats `1.5 eV/A` as a warning line, not a
  convergence target or an early-step failure criterion. The first five ionic
  steps are an allowed startup window. High force after that window remains a
  warning unless it persists for at least ten ionic steps without a decreasing
  trend, or is accompanied by independently verified abnormal displacement,
  periodic-image jump, or magnetic discontinuity. An `NSW=1` pilot can validate
  runtime, electronic, restart, magnetic, and immediate-geometry behavior but
  cannot establish persistent high-force failure.
- Alpha-Fe bulk relaxation: Gamma `15 15 15`, `ISMEAR=1`, `SIGMA=0.10 eV`.
- Alpha-Fe bulk convergence-reference static: Gamma `15 15 15`, `ISMEAR=-5`. This tetrahedron result remains the validated bulk benchmark. If a bulk total energy enters a slab/adsorption thermodynamic cycle, recompute the accepted bulk geometry with the dataset's matched Fe-metal final-static smearing branch instead of mixing the tetrahedron benchmark with slab energies.
- Corrected true Fe(110) fast screening: primitive 3x3 cell, five layers (45 Fe), two fixed bottom layers, Gamma `5 5 1`, and `EDIFFG=-0.05 eV/A`; use only for site screening, initial relaxation, and path exploration.
- Corrected true Fe(110) main production: primitive 3x3 cell, five layers (45 Fe), 15 A vacuum, bottom two layers fixed, Gamma `5 5 1`, `ISMEAR=1`, `SIGMA=0.20 eV`, `EDIFF=1E-5`, and `EDIFFG=-0.02 eV/A`.
- Corrected true Fe(110) ordinary NEB: use the same five-layer/`5 5 1` electronic branch with `EDIFFG=-0.05 eV/A`; refine the accepted CI-NEB/TS stage to `-0.02 eV/A`.
- Corrected true Fe(110) optional final static: Gamma `5 5 1`, `ISMEAR=1`, `SIGMA=0.10 eV`, and `EDIFF=1E-6`; retain only as an optional convergence check or legacy matched-static record, not as the active formal energy.
- Corrected true Fe(110) publication validation keeps Gamma `5 5 1`; any layer-count validation remains a separate branch and its energies cannot be mixed into the active five-layer dataset.
- Machine-readable authority: `configs/true_fe110_production.yaml`.
- Dataset consistency: all reportable clean-slab, adsorption, endpoint, reaction, and NEB data must use one selected slab thickness. Five and seven layers may coexist only inside the convergence study.
- Active selection: use five layers for the whole production dataset by explicit user decision. Five-versus-seven-layer comparisons, if run later, are validation only and do not change production automatically.
- Never combine energies from different branches or facets in one adsorption energy or barrier.
- Do not mix old non-current adsorption/NEB records into the corrected true
  Fe(110) `5x5x1` dataset.
- In the reviewed eight-paper Fe(110) sample, four and five layers are tied at three papers each; six of eight use four or five layers. C insertion and CO dissociation studies use seven or eight layers.
- chi-Fe5C2 and Fe3O4 bulk/surface systems retain the locked PBE/POTCAR/`ENCUT`/spin policy above but require their own convergence-backed k-mesh, smearing, magnetic ordering, DFT+U, and slab-geometry decisions. Do not combine their energies with the metallic Fe branch unless a thermodynamic cycle explicitly defines compatible references.

## 4. Mandatory Transition-State Search Gates

Follow `modules/transition_state_search/README.md`. NEB and DIMER are methods
inside one strategy; only a successful Grade-A record may become a transferable
TS template. Every path is bound to one normalized reaction contract, complete
identity atom map, explicit bond transformation, endpoint registry evidence,
and exact material/surface/method branch. Path review is checksum-bound to its
generated path plus `dist.pl` and `nebmovie.pl 0` evidence. DIMER and frequency
handoffs must retain those bindings. A reportable barrier requires registered
compatible IS/TS/FS final `TOTEN` values under
`fe110_converged_toten_sigma0p20_v1`, one compatibility fingerprint, and
hash-bound source outputs. Failed cases store failure constraints and
corrections only.

Template reuse separates method strategy from calculated results. A reviewed
Grade-A template with the same reaction family and a matching bond/site event
may transfer its waypoint, interpolation, NEB, DIMER, and local-frequency
strategy after passing the similarity threshold, even when endpoint IDs differ.
Only an exact compatible fingerprint may reference the existing registered
result. Structures, atom indices, modes, restart files, energies, and barriers
are never copied into a new result through strategy similarity.

For a DIMER-derived candidate, final TS acceptance requires DIMER technical
acceptance and the configured vibrational-frequency validation; bidirectional
downhill connectivity is optional diagnostic evidence and is not an acceptance
gate. NEB/CI-NEB candidates retain their existing source-method connectivity
policy.

TS frequency validation uses a contract-defined local finite-difference
partial Hessian by default for all reactions. Every reaction atom must be
active; directly coordinated surface atoms may be included when required by
the reviewed local mechanism. A full movable-slab Hessian is not mandatory.
Expand the local set only when the principal mode is ambiguous, local
surface-mode coupling remains unresolved, or the user explicitly requests it.
If vibrational thermochemistry is calculated, IS, TS, and FS must use the same
reviewed active-set definition, and the result must be reported as a
partial-Hessian correction.

`AUTHORITATIVE_NEB_EXECUTION_GATE` is the sole execution authority. Upstream
modules produce evidence only. Continue/stop/rebuild/submission/CI-NEB/DIMER/TS
or barrier actions without a current hash-bound `ALLOWED_ACTIONS` entry are
invalid, even when a lower-priority force or energy diagnostic appears healthy.

AQCat25 on `BUCT(sbq)` may accelerate endpoint relaxation, path initialization,
BA-Sella candidate search, and force-model fine-tuning only. Every GPU artifact
is a predicted candidate and must return through `work` using the hashes and
gates in `configs/execution_backends.yaml`. Only `sunboquan-codex` may run the
VASP/VTST calculation that supplies project energies, forces, relaxed
structures, paths, frequencies, and displacement evidence. GPU-to-VASP direct
transfer and automatic submission are forbidden.

## 4A. Transition-State Acceptance Gate

Apply only `docs/10_TS_VALIDATION_PROTOCOL.md`; saddle-search convergence alone is not TS acceptance.

## 5. Submission and Monitoring

```bash
ssh sunboquan-codex 'bjobs -a JOBID 2>&1'
```

NEB submission and stopping must go through
`scripts/neb_agent/submission.py` with a current
`AUTHORITATIVE_NEB_EXECUTION_GATE` decision. The executor uses
`bsub script.lsf`; documentation and monitors must not submit or stop jobs
directly.

- `PEND`: report queue state; do not claim VASP has started.
- `RUN`: inspect each intermediate image at bounded checkpoints such as ionic steps 3, 5, and 10.
- Separate SCF iteration stability from ionic force and geometry trends.
- Report unphysical contacts, path gaps, or persistent force divergence as
  evidence; only the authoritative gate may authorize stopping or rebuilding.
- Use the canonical compact monitor in `modules/transition_state_search/README.md`. Detailed output is opt-in only.

## 6. Close a Task

Use the state-management and version-control authorization rules in `AGENTS.md`.

## 7. Calculation Registry Gate

Apply only `docs/11_DATA_PROVENANCE_PROTOCOL.md`; backend and raw-file storage policy remain **Needs confirmation**.

## 8. Kinetics Post-Processing Software

CATKINAS and Zacros 4.0 are downstream consumers of validated kinetic data, not upstream scientific validators.

- CATKINAS: use for baseline mean-field MKM and coverage-dependent MKM scans after the kinetic-data, thermochemistry, and reaction-network gates pass.
- Zacros 4.0: use for surface-reaction KMC after the lattice/site model, event catalog, rate constants, diffusion rules, and detailed-balance checks are defined.
- Local paths, roles, required inputs, and expected outputs are recorded in `configs/postprocessing_software.yaml`.
- Do not pass hand-entered or unregistered DFT values into either tool.
- Record every input/output package through the calculation-registry protocol before accepting a post-processing result.
