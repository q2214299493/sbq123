# Fifteen C2 adsorption GPU candidates — producer completion

The explicitly approved CUDA v3 batch completed on physical GPU1 from
2026-10-13 11:36:36 to11:38:54 Asia/Shanghai (138.303seconds). Parent PID121917
has exited. This is an independent direct run, not a Slurm job.

All15 producer exits are zero, all15 actual model tensor records show cuda:0
bound to physical GPU1, and all15 reach the unchanged ML fmax target0.10eV/Å
within19–74 LBFGS steps. Seventy-five original-byte outputs were collected;
remote/local SHA256 hashes and return manifests pass for all15. Atom order,
cell/fixed-atom producer invariants and returned Selective Dynamics flags pass.

Preliminary covalent-distance/H-placement checks retain the target graph in12
candidates. 06_A and06_B have detached or multiply connected H under the existing
signature parser;09_B has a changed adsorbate graph/H placement. These three
need chemical review/repair, not automatic VASP handoff. The parser verdict is
screening evidence, not bond-order analysis or proof of thermodynamic stability.
Keep all original evidence-required seeds; ML alone cannot delete their motifs.

No complete surface-aware final duplicate review, VASP optimization, reportable
adsorption energy, model promotion or quantified VASP acceleration claim exists
for this new set. Fifteen ML convergence passes do not prove fifteen distinct
stable adsorption states. CPU v2 outputs remain preserved and predicted-only.

Evidence is under
`calculations/fe110_c2_adsorption_06_10_20261012/gpu_direct_v3/`:
`direct_batch_exit_record.json`, `return_validation.json`, `output_inventory.json`,
each candidate's `output/job_direct-fe110-c2-0610-20261013-v3/`, and the canonical
`registry_completion_*` receipts. GPU workflow is recorded done, scheduler
UNKNOWN/NONE and no numeric scheduler job ID. Accepted energy tables are unchanged.

See `fe110_c2_cuda_restart_20261013.md` for device binding, approved restart,
source/parameter preservation and executed tests. Next step is final structure
and surface-aware duplicate review, with separate authority for VASP submission.
