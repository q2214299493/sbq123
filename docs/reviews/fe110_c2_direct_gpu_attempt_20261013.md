# Direct execution attempt for fifteen C2 adsorption candidates

User authority: “你试试”, in response to the proposed direct GPU1 serial run.
Default Slurm execution remains unchanged. The explicit backend exception is
limited to these fifteen frozen candidates, GPU1 UUID
`GPU-450609b3-d1fd-ac33-d03a-79891be402da`, four CPU threads and a 7200-second
batch bound. No shared service, other user's process, VASP job or checkpoint
was changed. A cooperative file lock is not an administrator GPU reservation.

## What actually happened

- v1 no-model preflight rejected a logical/canonical path mismatch. MZ73's
  `/home/sbq` is a verified symlink to `/home/ubuntu/hdd/sbq`. Its evidence is
  retained; no model was launched by v1.
- v2 preserves the old candidates/model and recognizes the same authorized
  directory after canonical resolution, without widening the write boundary.
  Its local and remote no-model preflights passed. Derived wrappers use a
  `direct-...` ID, never a fake `SLURM_JOB_ID`.
- Detached v2 process started: run ID `direct-fe110-c2-0610-20261013-v2`, PID
  `114670`. Original-byte launch/started records were collected. GPU input
  registration and actual process launch were canonically recorded.
- Startup verification found LBFGS steps for 06_A, but no model compute process
  on physical GPU1. The actual deployed `OCPCalculator` constructor defaults
  `cpu=True`; the copied runtime's `patched_calc(...)` omitted `cpu=False`.
  This is an actual CPU model execution, **not GPU acceleration**. 06_A
  producer completed and 06_B subsequently began. Producer completion alone
  does not establish convergence, intact chemistry or stable adsorption.
- No historical GPU run is automatically reclassified from this observation.
  The defect is established for this copied adsorption execution entrypoint;
  other historical entrypoints require separate evidence.

## Correction prepared; no CUDA restart yet

`scripts/adsorption/direct_gpu_batch.py` now rejects a model runner without
explicit `cpu=False` before loading weights. It checks actual model tensor
device and the single visible physical GPU UUID, and requires each successful
candidate to retain `execution_device.json`. CUDA availability or a GPU label
alone cannot establish GPU execution.

The source correction is prepared in
`calculations/fe110_c2_adsorption_06_10_20261012/gpu_direct_v3/runtime/relax_endpoint_candidates.py`:
explicit CUDA calculator creation followed by a tensor-device assertion before
optimization. It preserves structures, checkpoint, optimizer, force threshold
and step budget. v3 is **not yet frozen, deployed or executed**.

The active v2 CPU attempt was not stopped without separate user authority.
An explicit question asks whether to stop only PID114670 and its own child
process groups, preserve outputs, then freeze and preflight the CUDA-corrected
v3 package before launching GPU1. Do not touch other users' jobs or services.

## Evidence and validation

- `gpu_direct_v1/remote_direct_preflight.json`: preserved failed input preflight.
- `gpu_direct_v2/direct_request.json`, adapter provenance, batch manifest and
  remote preflight: exact authorized inputs and source derivation.
- `gpu_direct_v2/direct_launch_receipt.json`, `direct_started.json`: original
  producer process evidence, not scheduler accounting.
- `gpu_direct_v2/registry_input_*` and `registry_launch_*`: canonical plan,
  approval and receipts. One batch calculation tracks fifteen candidates.
  Actual launch records scheduler NONE/job ID null, scheduler status UNKNOWN
  and the separate CPU-device warning; no accepted result inserted.
- Current scoped Python syntax, Ruff and 25 device/backend/handoff tests passed.
  CPU-default/explicit-CPU negative tests prevent this specific repeat.
- CUDA model loading/inference, final geometry, convergence, and speedup are
  not yet validated. Full repository tests were not run.

The existing global state-sync conflict at
`sbq_catalyst_agent_workflow.egg-info/PKG-INFO` remains unrelated and unrepaired.
