# CHCO force coverage comparison

Both arms used the frozen AQCat25 FT512 base, a force-only loss over the same
31 movable atoms, seed 0, AdamW, batch size one and 100 actual optimizer
updates on the same BUCT3 RTX 4090. The control used point 12 on every
update. The joint arm cycled through points 9, 10, 11 and 12 in order, using
each 25 times. Both final checkpoints used identical per-update learning
rates, with a peak of 0.0001. Points 7 and 8 were evaluated only after both
checkpoints were finalized.

The initial job (566) exposed a learning-rate mismatch. Equiformer initializes
the scheduler from the original loader length. The corrected worker inserts
the one-step sampler before the scheduler is initialized. Both corrected
fits in job 567 completed 100 updates and produced verified checkpoints with
identical LR traces. That job's evaluation stopped at the CPU-default guard.
Job 568 explicitly used GPU inference on those exact checkpoints. It completed
with native Slurm exit 0 and both predicted force tables were independently
compared against the original accepted force vectors.

| Validation point | Single maximum error (eV/Å) | Joint maximum error (eV/Å) |
|---|---:|---:|
| 7 | 0.17789496 | 0.04367511 |
| 8 | 0.04031529 | 0.04394655 |

The maximum across the two validations decreased by 75.30%. Point 7 improved
and point 8's worst-atom error increased by 0.00363 eV/Å. In the joint arm
the largest vector error was on movable Fe atom 22 (one-based) at both
geometries. This supports local coverage as a contributor to the earlier
oscillation. The limited holdout cannot establish general transferability or
whether a new candidate will meet the DFT movable-atom force target.

The code and inputs are separate from the existing single-label protocol.
The submission receipts, hashes, raw force comparisons and final verification
are retained in the case's `chco_force_coverage_20261119_lr_matched` directory.
No new DFT point or scientific promotion was made. A candidate would first
need a separate joint-model BA-Sella search and geometry review. The DFT
stopping test remains a raw movable-atom maximum force below 0.03 eV/Å.
