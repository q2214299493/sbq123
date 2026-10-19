# Authorized corrected adsorption training retry

User request: 修复好再跑一次

One new corrected attempt only: control then treatment on MZ73 GPU1,
each at most two epochs,496 steps,30 minutes;total at most60 minutes.
Reuse the frozen original model,physical labels,whole-job split,and sampling
recipes. Fix the force-only DDP graph dependency and numerical POSCAR decoding
comparison. Observe the first two native CUDA backwards within the same
training process without extra steps or optimizer reset. No automatic retry,
heldout model evaluation,model promotion,VASP,or shared-service changes.
Preserve the failed v1 package and all evidence;use a new v2 directory.
