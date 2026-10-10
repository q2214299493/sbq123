# Fe(110) C2 adsorption acceleration adjustment

Goal: reduce compatible VASP relaxation work and total compute elapsed time,
not merely reach a small ML force. User authorized local workflow adjustment;
no new scientific job, training, stop or VASP parameter change in this step.

## Evidence and diagnosis

The old handoff uses AQCat25 pre-relaxation to 0.10 eV/Å, followed by VASP to
the unchanged 0.02 eV/Å production criterion. On five exact initial structures,
AQCat max forces were 0.052–0.099 eV/Å while VASP max forces were
0.383–0.479 eV/Å. A small ML force was therefore not a DFT readiness guarantee.
Existing diagnostics sampled only initial/final frames, leaving much of the
observed DFT rearrangement unsampled. These observations support targeted
model adaptation; they do not prove that fine-tuning will shorten relaxation.

MatRIS2180 improves sampled C/O errors but worsens final Fe/H errors. It is
not automatically substituted as adsorption primary. Preserve the frozen
AQCat25 baseline and compare any new checkpoint, including the Fe/H response.
Do not freeze more Fe, constrain the adsorbate into its intended graph, loosen
DFT convergence, or silently change the final adsorption state to claim speed.

## Completed local preparation

Read existing completed OUTCAR/XDATCAR/OSZICAR files from seven jobs; no VASP
rerun. Select early, quarter/mid/late, penultimate and final frames, at most
eight per job. The whole-job split was fixed before prediction/training:

| Role | Jobs | Frames |
|---|---|---:|
| Training candidates | 01_cfg1, 02_cfg2, 04_cfg2, 05_cfg0 | 32 |
| Development validation | 04_cfg0 | 8 |
| Frozen held-out candidates | 04_cfg1, 05_cfg1 | 16 |

`calculations/fe110_five_c2_adsorption_20261006/adsorption_acceleration_rebuild_v2/`:

- `dataset_review.json`: 56 exact source-bound structure/force label candidates,
  total energies for force-label use only, available total magnetic moments.
- `geometry_split_review.json`: all selected graphs preserved, no hard overlap,
  original bottom-18-Fe fixed coordinates preserved; no cross-split strict
  equivalent structure fingerprints. Near-duplicate/site review remains open.
- `acceleration_adjustment_plan.json`: frozen checkpoint, dataset/review hashes,
  replay candidate and comparison design. **Not an executable training bundle.**

Each selected force frame has explicit EDIFF termination, matching electronic
cycle/ionic step, complete finite forces, matching OUTCAR/OSZICAR energy, and
XDATCAR coordinates checked against printed OUTCAR precision. Source output
hashes and force-table byte ranges are preserved. Whole source jobs have normal
termination/required-accuracy evidence; intermediate frames are not converged
endpoints. Atom order, cell and actual species-dependent C/O/H ordering remain
unchanged. Train/development/held-out assignments never divide one source job.

The initial read-only collector exceeded 180 seconds. Its request/failure is
retained in `adsorption_acceleration_rebuild_v1/`. The revised reader removes
per-line tail-buffer copying, reads the bounded footer once and streams partial
output to preserved files. v2 completed successfully; no scientific job was
retried. Local SSH/file-size check found a 33.5 MB example OUTCAR and an intact
connection, so there is no basis for calling this timeout a model/VASP failure.

## Adjusted loop and performance test

1. Complete near-duplicate/site and replay compatibility/source-binding review.
   The 13 old calibration records are only a replay **candidate**; remote source
   paths are not local files. Their current SIGMA branch/bindings must be checked
   before training. Do not import them merely because calibration once passed.
2. Adapt the training input for adsorption trajectories rather than mislabeling
   them as TS force labels or converged adsorption endpoints. Prepare one
   adsorption-scoped AQCat25 candidate, preserve the baseline, and require
   separate GPU training authorization. MatRIS remains an audit alternative.
3. Inspect C/O, movable Fe/H, direction errors and near-DFT-minimum drift on
   the reserved structures. Do not promote using Fe-dominated aggregate RMSE.
   Retention tolerances/training settings need review; none are invented here.
4. On two reserved examples, compare raw-seed direct VASP, frozen AQCat25 plus
   VASP, and candidate-checkpoint plus VASP. Start GPU arms from the same raw
   seed. Reuse existing controls only if source, parameters, resources and
   recorded timings match. No pilot or new VASP calculation is launched here.
5. Require the same reviewed final chemical state/minimum and unchanged DFT
   criteria. Report both steps and actual VASP runtime; add GPU, incremental
   training and labeling cost. Show first-case cost, declared amortization and
   break-even count separately; exclude queue wait from compute timing.

The implemented accounting helper is
`scripts/adsorption/acceleration_benchmark.py`. It rejects unmatched seeds,
compatibility/resource signatures, different reviewed minima and incomplete
or unreviewed runs. It cannot authorize jobs, scientific acceptance or model
promotion. Reduced steps with larger total cost is not acceleration success.

## Limits

No checkpoint trained/promoted, no paired speedup measured, no new GPU/VASP
submission. CH–C–O species03 remains outside this dataset. Same-family,
different-job held-out data do not by themselves establish broad chemical
generalization, especially if approximate/symmetry-related duplicates remain.
The preparation is scoped to this C2 adsorption campaign; TS paths and global
backend roles are not changed.

Next executable step: complete adsorption training-input adaptation and
near-duplicate/replay review, then present one bounded training request for
authorization. Only subsequent independent and matched runtime tests can
establish improved acceleration.
