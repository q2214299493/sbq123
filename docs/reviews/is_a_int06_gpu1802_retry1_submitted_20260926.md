# IS-A → INT06: authorized environment-only GPU retry1802

User authorized “提交” after the confirmed TMPDIR bootstrap failure. Job1802
was submitted once on MZ73, with TMPDIR=/home/sbq/sbq/aqcat25/tmp and a fresh
output/run2. GPU1793 and output/run1 remain untouched.

The scientific request is unchanged:
`6011d0a9b1a0430e3b273b9180f2d6484683589a81def2d168418696e8bf4d32`.
Eleven images, frozen MatRIS epoch6 primary, AQCat25 exact final-path audit,
ordinary ML-NEB only, max400 steps, fmax0.10 eV/Å, no added H/O-H/C-C restraints,
no automatic retry/fine-tuning/VASP. One GPU, four CPUs, 40GB host memory, two hours.

Repeated remote model-free preflight verifies request/images/runtime/model hashes.
Live scheduler evidence reports RUNNING. The job log confirms request checksum
verification after the wrapper environment setup: the prior TMPDIR boundary
failure has not repeated. At this initial checkpoint no optimizer convergence
or scientifically accepted TS is claimed; model startup and path progress need
their own runtime outputs.

Before submission all GPUs had 6–8GB free, with unrelated processes using much
of the memory. The frozen AQCat25 checkpoint is121MB; its file size is not a
validated peak-memory requirement. Available memory is nonzero but runtime OOM
risk remains unverified. No external process was changed, stopped or preempted.

Package: `calculations/fe110_c2ho_h_to_c2h2o_ts_20260822/h_migration_is_a_int06_path_20260926/gpu_execution_20260926`.
Next: collect GPU1802 producer completion/failure and complete path evidence;
review geometry/peaks and the identical AQCat25 audit before preparing VASP.
