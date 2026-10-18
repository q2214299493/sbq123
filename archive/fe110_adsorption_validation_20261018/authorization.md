# Authorized validation

The user said “验证” after being told that the next action was16 frozen heldout
force predictions plus3 existing VASP-reference geometry comparisons.

Scope: one GPU1 validation on MZ73, baseline versus frozen candidate2185,
sequential execution, original seed80-step cap and DFT-minimum20-step cap,
ML fmax0.10eV/Å, maximum1800seconds. Slurm remains failed; execution uses the
existing private-directory direct-run pattern with a new exact backend exception.
No shared service is changed and no other user's process is stopped.

No new training, checkpoint change, VASP calculation, automatic retry, model
promotion, energy-ranking calibration or acceleration claim is authorized.

The local-only v1 package failed a Windows GBK/UTF-8 policy-file read before
deployment or any GPU execution. Its files remain intact. The UTF-8-corrected
v2 request is a fresh binding; only v2 was deployed and run.
