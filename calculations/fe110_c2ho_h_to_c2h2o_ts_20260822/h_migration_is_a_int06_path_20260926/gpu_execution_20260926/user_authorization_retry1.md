# Environment-only retry authorization — 2026-09-26

User statement: “提交”, in reply to the confirmed GPU1793 TMPDIR startup
failure and request to resubmit with only that environment fix.

Authorize one MZ73 GPU run with TMPDIR=/home/sbq/sbq/aqcat25/tmp and fresh
output/run2. Preserve GPU1793 output/run1 and its failed scheduler/producer
records. Exact scientific request SHA-256 remains
`6011d0a9b1a0430e3b273b9180f2d6484683589a81def2d168418696e8bf4d32`.

Unchanged: 11 images, MatRIS epoch6 primary, AQCat25 exact fixed-path audit,
ordinary ML-NEB, maximum400 steps, fmax0.10 eV/Å, one GPU/four CPUs/40GB/two
hours. No new coordinate restraints, ML-CI, fine-tuning, automatic retry or
VASP submission. GPU outputs remain predicted candidates pending work review.
