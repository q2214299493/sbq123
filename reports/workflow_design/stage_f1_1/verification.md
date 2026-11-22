# F1.1 verification and limits

**Scope.** This inventory covers checkout `6dbc0fb35223cc832abc2fc19bc0ca6de54f4411`, its relation to the three named ancestor refs, the scientific input and result contracts listed in [the inventory](contracts.md), and the three explicit research cases. Nine Markdown reports in this directory are the complete task change. The [index](README.md) maps them to all twelve requested deliverables.

## Checks actually performed

| Check | Result |
| --- | --- |
| Branch heads and changes | Queried the four heads on `sbq123` and compared their Git ancestry and adjacent file changes. All four matched the supplied IDs. The V.1 evidence commits descend from the R.2.5 runtime. |
| Contract and entry-point inspection | Read owner definitions, CLI argument parsers, native assembly/gate paths and existing tests. Compared strict V1 bundles, partial network definitions, integer-v1 intake and V2.0/V2.1 output validation. Traced project YAML, task YAML, catalog project, ticket, priority source list and run manifest to their individual consumers. |
| Fe evidence | Independently matched 11 raw file digests in the development evidence workspace to the published inventories: three CONTCAR, three OSZICAR, three electronic OUTCAR, and VFA POSCAR and OUTCAR. The publication checkout carries the inventories; the raw files checked here reside in the separate development workspace. The existing network CLI test reproduced the archived draft. |
| Ni/Cu and oxide | Checked network identity and native normalization, read the accepted single-point manifest, inspected stable DRC rows, and compared the oxide graph, consumed receipt, fatal code and corrected text. The case pages include the actual checkout hashes of their published sources. |
| Windows offline pytest | **139 passed** in 11.84 s. Exact command below. Includes byte-for-byte reconstruction of ten published rate outputs and both qualification files from archives (two CATKINAS cases and eight Zacros trajectories). |
| State Manager | Startup `audit --phase start` reported existing managed projection drift in `docs/06_MODULE_MAP.md#module_row:transition_state_search`. The read-only `sync --safe-only` returned code 2 with `state history source changed before proposal generation`. Before/after file sets and SHA-256 matched for 352 State Handoff event/cache and selected projection files. No new proposal ID or review choice was returned. |
| Report validation | Checked relative links, evidence hash tables, and the staged file list and whitespace. All task-owned changes are Markdown under the requested directory. |

The Windows command ran with Python from `C:/Anaconda/python.exe` in the isolated F1.1 worktree. Arguments are shown in PowerShell array form for reproducibility.

```powershell
$cases = @(
  'tests/test_multiphase_identity.py'
  'tests/test_scientific_intake.py'
  'tests/test_inventory_accounting.py'
  'tests/test_rate_network_binding.py'
  'tests/test_oxide_bridge_topology.py'
  'tests/test_zacros_zero_event_native_receipt.py'
  'tests/test_mkm_analysis.py::test_closed_cycle_evidence'
  'tests/test_mkm_analysis.py::test_draft_inspection'
  'tests/test_reaction_network.py::test_cli_reproduces_versioned_fe110_artifact'
  'tests/test_b1_contract_acceptance.py::test_ten_outputs_and_both_qualification_files_replay_byte_for_byte'
)
C:/Anaconda/python.exe -m pytest -o addopts= -q @cases
```

## Interpretation limits

- The runnable boundary here is offline parsing, validation and replay. No native solver or VASP-family calculation was launched, no scientific acceptance or execution authorization was granted, and no production database was written.
- The Fe endpoint search and thermochemistry conclusions are inherited from the bounded V.1.2.1 assessment. F1.1 checked identity of selected local sources. It did not repeat the literature search, inspect remote schedulers or prove that no external endpoint frequency data exist.
- Native output replay verifies reconstruction of published artifacts. It does not qualify new native inputs, establish general applicability of synthetic models, or supply unmeasured uncertainty.
- Entry-point coverage is limited to the named project, intake, identity, evidence, kinetics, engine and analysis paths. Discovery of a calculation-local research layout is evidence for human reuse. The finding about a missing common reader is bounded to the inspected tracked code and configuration.
- The full Windows repository suite, Linux CI, and an executable F1.2 project reader were outside F1.1. Existing unrelated worktree changes and the State Manager discrepancy stay with their owners.
