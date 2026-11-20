# Fe(110): supplied MACE checkpoint pilot

## Scope

The first trial used the supplied `fe-c-o-mace.model` (`Default` head,
H/C/N/O/Fe; exact digest in `configs/mace_fe110_pilot.yaml`). Its reference
functional and training-set membership are unverified. The official
[MACE-MH-1 model card](https://huggingface.co/mace-foundations/mace-mh-1)
lists a surface-adsorbate `oc20_usemppbe` head; it was considered as a
fallback, not run in the trial. New package versions alone do not establish
model accuracy.

The user's same-coordinate CO comparison spans three fixed Fe(110) geometries.
From the six printed C/O magnitudes the MAE of force **magnitudes** is
0.05080 / 0.33249 / 0.15530 eV/Å for supplied MACE / AQCat25 / the right-hand
model identified by the user as MatLS. MACE is closest in five of six rows;
long-bridge C is the exception. This is not a vector, path, or speed benchmark.

## Local CPU results

Local outputs are under `outputs/fe110_mace_surface_pilot_20261120_v2/`.
No model artifact, raw VASP output, or runtime output is published.

- A first load stopped before inference because an e3nn nested TorchScript
  load retained CUDA placement. The CPU pilot remaps that load only during
  checkpoint setup; source bytes and weights are unchanged.
- `adsorption_review.json`: two FIRE steps from the reviewed CH+CO initial
  structure, ML movable-atom maximum force 0.3359 → 0.2488 eV/Å, maximum
  displacement 0.00869 Å, fixed layer preserved. Not ML converged.
- `path_review.json`: two ordinary ML-NEB steps, all 8 images retained,
  maximum adjacent RMSD 0.1041 Å and numeric continuity checks passed. The
  maximum projected force decreased from 1.3677 to 0.8281 eV/Å; not converged.
  Image 05 is the strict internal peak of this short trial; not a TS or barrier
  result. CI was not started.
- `active_learning_review.json`: resumed only the label-review phase with the
  above path. Five-decimal OUTCAR Cartesian coordinate printing allows half a
  printed unit per component (plus cell rounding); all six bound geometries
  match under that check. Inference uses the actual OUTCAR force coordinates.
  Existing VASP force vectors compared, 6/6; no new labels or training.

| Reaction | IS adsorbate vector MAE | TS adsorbate vector MAE | FS adsorbate vector MAE |
|---|---:|---:|---:|
| CH + CO | 0.1927 | 0.1637 | 0.7999 |
| INT06 → MID | 0.6647 | 0.6669 | 0.7254 |

Vector MAE is the mean Euclidean norm of the per-atom force difference,
in eV/Å. The maximum movable-atom vector error across these references is
1.5263 eV/Å. On the CH + CO product the predicted relative energy is 1.1077 eV
vs VASP 0.6593 eV (each relative to its own IS). These are fixed-geometry
comparisons, not new barrier or optimized adsorption values. The five
selection suggestions (02–06) are path-coverage/peak/RMSD candidates, not
uncertainty or authorized VASP labels.

## Decision

Keep validation-only status. No existing checkpoint was replaced and no VASP,
remote GPU, or training job was submitted. These geometries are existing
references, not verified independent held-out structures; throughput and
relative accuracy outside the user's CO test remain unverified. Before any TS
promotion, benchmark the three checkpoints on the same off-minimum VASP-labelled
structures using force vectors, relative energies, and retention of the
intended path. Reuse the existing labels first; keep calibration and training
decisions separate.
