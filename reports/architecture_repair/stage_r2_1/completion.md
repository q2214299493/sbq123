# R.2.1 · V2.1 network-bound rate validation

R1-001 is repaired in the explicit network-qualified API and CLI. Baseline `335008915ebcb227cc5012054df105a2e0ac4404` is the direct repair parent. The [audit commit](https://github.com/q2214299493/sbq123/commit/efe4cf4e2a0e0f6f1c94af66f8729c078906db25) supplied the finding. The independent development branch at `233d5a6c` had 242 unstaged modifications, three unstaged deletions and 1,100 untracked porcelain entries at intake. All edits and tests ran in the isolated repair worktree.

## Cause and repair

The previous validator used the supplied network to verify its canonical version and site inventory. It reconstructed source terms from the rate record's own stoichiometry. A modified record could therefore agree with itself while attributing the source to the wrong reaction, species or parameter. The native producer already matched its model directions and parameter selection to a network entry. Its membership check now lives in a shared binding implementation used by both producer and strict reader. Existing reaction indexing, direction construction, catalog scope, field schemas, source projection and dimensional checks remain with their owners.

Use `python -m scripts.rate_output_v2 OUTPUT --qualified-network NETWORK`. By default the expected scope is the entire supplied network. For a chosen study subset, pass its IDs independently, e.g. `--reaction-id ads --reaction-id transfer`. The validator requires exact set equality, rejects duplicates and unknowns, and preserves the order in the supplied record.

| Binding | Checked rule |
| --- | --- |
| File and network | Decode and hash the same byte buffer. Match the raw artifact digest in provenance, canonical network version, project and reference scope. |
| Reaction | Resolve one unique network definition for each selected ID. Type, surface IDs, phase IDs and interface ID come from that definition. Validate their schema and catalog relationship. V2.1 has no separate row fields for overriding them. Check participant species and vacancy inventories in that scope. |
| Parameter | Both the entry's declared membership and the indexed parameter's own reaction ID must match. Check the parameter's directional fields and require a bound direction for a numeric observation or coefficient. |
| Direction and multiplicity | Use the network builder's direction convention. Require exact forward reactants/products and vacancy consumption/release maps. Check stored reverse orientation against the definition, directional applicability, signed net progress and reported sources. Unknown reverse remains null, irreversible reverse is excluded, and reversible unobserved flux can remain null. |
| Identity and scale | Read-only validation keeps the run, dataset, coefficients, activity orders, ordering, units and denominator. Strict qualification requires output binding. For producer-defined `rates-` IDs it checks content identity. Opaque IDs and observed numerical values require separate producer evidence to authenticate. Network qualification checks the signed orientation and consistency of observations. It does not establish the measured magnitudes or the scientific validity of a rate law. |
| Compatibility | Network-free V2.0/V2.1 retain shape, dimensional and arithmetic checks as applicable. Existing API `network=` and CLI `--network` retain catalog semantics. CLI alias `--catalog-network` makes that scope explicit. No schema migration or engine changes. |

## Before/after and independent checks

The new tests use a hand-defined one-reaction subset, independently compute its species/vacancy ledger and recalculate its envelope ID. Each row mutation below retains the exact original network and SHA-256. Both API and CLI are exercised for the shape-valid negative rows.

| Case | Original/catalog behavior | Network-qualified behavior |
| --- | --- | --- |
| Changed reaction ID, including an existing reaction outside the requested subset | Accepted by the preserved catalog check | Rejected |
| Changed product/reactant coefficient, substituted cross-inventory species, swapped signed sides | Accepted when source ledger agrees | Rejected |
| Unknown parameter ID or parameter belonging to another reaction | Accepted | Rejected |
| Excluded forward direction with internally consistent negative progress | Accepted | Rejected |
| Changed vacancy consumption, release or site multiplicity | Accepted for known inventory IDs | Rejected |
| Correct strict subset supplied by caller | Scope limited to site catalog | Accepted. Missing, extra or repeated subset members rejected |
| Absent network, changed file bytes, absent output binding, altered run under original content ID | Shape mode has no file binding. Historical CLI with network already rejects a raw-digest mismatch | All four rejected |
| Valid forward-only and unknown reverse fixtures | Representation and arithmetic checks only | Valid fixtures pass. Replacing either excluded or unknown reverse with numeric zero fails |
| Inconsistent phase/surface/interface/type, parameter owner or missing directional binding inside a separately reversioned network fixture | Outside catalog-only reaction checks | Rejected |
| Historical V2.0 / V2.1 | Accepted in their supported modes | Network-free behavior retained. Strict qualification requires V2.1 |

## Verification

On Windows, pre-change `test_rate_output_v2`, `test_rate_dimensions`, `test_native_rate_adapters`, `test_b1_contract_acceptance` and `test_b1_native_acceptance` passed **219/219**. The post-change run included those five plus `test_rate_network_binding`, `test_kinetic_parameters`, `test_reaction_network`, `test_stoichiometric_sources`, `test_multiphase_contracts`, `test_interphase_transfer` and `test_cross_phase_elementary` under `tests/`. **509 passed**, with no focused baseline failures. All five changed Python files passed py_compile and Ruff. The full repository suite and Linux execution were outside this run.

`test_b1_contract_acceptance.py::test_ten_outputs_and_both_qualification_files_replay_byte_for_byte` replays both adapters and compares serialized output bytes. The two CATKINAS outputs retained their reference-site-pair denominators. The eight Zacros outputs retained their simulation-cell denominators. All ten independently passed the strict file API in a fresh Python process that raised on any import under either engine namespace. No native executable ran. Hashes below identify the unchanged archived payloads.

| Archive | SHA-256 |
| --- | --- |
| catkinas-phase2_5_2 | `e1a71272fc19b0f8756e4fcb64ad7ef2e3b83eac9572290b27cef1005bc17e77` |
| catkinas-phase3_0 | `eb73c3b756ad88316b792df4919c0e08cbe9e0967bcd4d6e2277a5eefcac2ec6` |
| zacros-attractive | `5e3d6a6708edb73208fe59cc3797b1d4bfbae6a044bbc8b4ae3ba0b0a9d08d44` |
| zacros-continuous | `f24c5f8b7def7aa89a95ccd0efd36f312084b1da09c5060d94e35df31aeaf330` |
| zacros-dent | `4fbd954adbfe88a1d65a8d40719ab56aca19db088029089b21f96e2720e1ecbf` |
| zacros-full | `dafa3b41d823c144b30be119690be1f1df50b9518958f5686e0f45c774ece404` |
| zacros-interacting | `73e1524fa096e0ffc6cef24c3e2638bdc497a195975e2b8dff67453be1fe075b` |
| zacros-mono | `5d96357c05c3f5782f23818f0071330dd199b09e82e79b82f5d05eedf7d99367` |
| zacros-resume | `c210a6448ae8fac95aa29d00717e2f40824e76daf539ed12f378fd4331cd6981` |
| zacros-split | `f0c85072c95cc5c6a6de46fbe93411001fc271b30bd6c89b91193e7785e68f82` |

## Changed files and handoff

- `scripts/rate_output_v2.py` adds the qualified reader and preserves catalog-only calls.
- `scripts/kinetic_data/network_binding.py` owns the shared row binding.
- `scripts/kinetic_data/native_rate_output.py` invokes that same check after native envelope construction.
- `scripts/multiphase_contracts.py` exposes the existing duplicate-key decoder for a single captured byte buffer.
- `tests/test_rate_network_binding.py` contains independent binding regressions and archive qualification.
- `modules/kinetic_data/multiphase_contracts.md` documents the API and CLI modes.
- `reports/architecture_repair/stage_r2_1/completion.md` records this repair.
- `modules/state_handoff/events/history-stage-r2-1-network-rate-binding-20261122.json` records the history proposal for review.

The existing transition-state module-map projection drift was observed at startup and is independent of R1-001. The State Handoff proposal requires a separate decision. Only the proposal command was used for handoff, since this baseline's safe-only sync can record an approval through the Registry/Excel reuse path.
