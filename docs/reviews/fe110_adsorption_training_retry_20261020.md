# Corrected adsorption training retry — 2026-10-20

## Scope and repair

User explicitly requested `修复好再跑一次`. This authorizes one new attempt,
not automatic retries. The v1 failed package and its exit evidence remain intact.
The repaired role loss has a zero-coefficient energy-output graph dependency
for native one-rank DDP. No energy fitting,force-target,weight,sampling,DFT,
structure,split,checkpoint or budget change was made.

The canonical DB preflight now accepts only coordinate decoding roundoff up to
`1e-12 Å` with zero relative tolerance;cell/PBC/raw forces/roles and source-file
hashes remain exact. This replaces the supplementary v1 RAM-only comparator
in this newly bound package,not in the old frozen package.

## Fresh bindings

- Remote: `/home/sbq/sbq/adsorption_training_comparison_20261020_v2`
- Run: `direct-adsorption-role-ab-20261020-v2`
- Direct request: `78e6ae1c5611b747a035e92cf4b1bfb4308129f80460ea1fc2d28c83177ca555`
- Comparison: `beb6f086c16409d2f3983feb874bb142f79fa8f03e5cefff708b51475a89c3af`
- Control: `8465cdd7e5696242d15eb5bb221310c7c90b6662402e72be1bececb280be9578`
- Treatment: `59c90094bbdbb3e5cc6c7611f9b80314c8383d02864eb56c7a45893015c0010e`

Original physical data and per-arm recipes are copied byte-for-byte. Only
the new runtime bindings and absolute dataset locations change. Both arms
start from the same original AQCat25 checkpoint,248train/60development,
seed42,batch1,learning-rate1e-5,2epochs/496steps each. The46newheldout and
16observedheldout remain outside fitting and epoch selection.

## Execution checks

180 scoped tests,compilation and scoped Ruff passed before launch. These are
software checks,not model accuracy or acceleration evidence. Actual MZ73
CPU on-disk/native-CLI/checkpoint preflights passed for both arms. GPU1 was
idle with24066MiB free at the resource check;other GPU processes were untouched.

ControllerPID2893515 launched at2026-10-20 00:45:38CST;controlPID2893524.
Physical GPU1 UUID`GPU-450609b3-d1fd-ac33-d03a-79891be402da` is the only
visible device. Direct mode has no scheduler job ID and does not emulate Slurm.

The first two native backwards are observed within the actual training
process. The observer does not add steps or reset an optimizer. It records
actual optimizer-step hook calls separately from native iterations because
AMP can skip an update. The receipt must prove the energy-head gradients
are present and exactly zero before the run is accepted as completed.

Each arm has30minutes,total60minutes,one GPU,4CPU and32GiB RAM. A producer
failure stops the batch without retry or starting the next arm. No VASP,
heldout prediction,automatic promotion or measured-speedup claim is authorized.

Evidence root:
`calculations/fe110_c2_adsorption_06_10_20261012/adsorption_training_direct_20261020_v2/`.
Current producer status belongs to its returned receipts and current-task event;
launch success alone does not establish completed training or useful accuracy.
