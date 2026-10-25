# User authorization: exact Fe(110) grouped14 submission

The assistant asked: “是否提交这14份任务？” with the reviewed scope of12 new
single-point force labels and2 bounded optimizations, each32MPIranks, estimated
combined867.78–1022.75allocated core-hours, without queue guarantees.

The user's direct reply was: **“1提交”**.

This authorizes submission of exactly the14 cases in
`calculations/fe110_reico_pilot300_20261022/grouped_inputs_20261025_v1/plan.json`:

- Single points: family_0010_step015, family_0021_step004,
  family_0022_step006, family_0024_step007, family_0033_step005,
  family_0041_step016, family_0048_step005, family_0055_step015,
  family_0061_step005, family_0072_step007, family_0079_step014,
  family_0097_step017.
- Optimizations, at most80ionic steps each: family_0099_step020 and
  family_0023_step020.

Use only `sunboquan-codex`, the reviewed unchanged input bytes and native
execution gate/executor. Respect the account128core limit through LSF;
recheck runtime, source/target POTCAR hashes, input bundles and fresh target
reservations. Queueing is distinct from starting or scientific convergence.

The2 reserve points, paused05/07C3sources, automatic retries/continuations,
other calculations and model training remain outside this authorization.
Submission metadata may be recorded through the canonical reviewed registry
workflow; no accepted scientific results are authorized by submission.
