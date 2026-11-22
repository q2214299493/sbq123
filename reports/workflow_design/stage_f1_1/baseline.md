# Branch reconciliation

Compared the four remote refs directly with `git ls-remote --heads sbq123`. For each adjacent pair below, `git merge-base --is-ancestor EARLIER LATER` returned 0. The refs form one ordered ancestry chain. The reverse direction would give the wrong answer to whether production includes the later work.

| Remote branch | Actual remote HEAD | Difference from preceding row |
| --- | --- | --- |
| `codex/multiphase-phase0-integration` | `dd3a5cbbd180c97fe09a0554a6ef2a845ef95f73` | Deployed-line comparator identified by the task. It predates the integrated R.2 repair series. |
| `codex/stage-r2-5-release-qualification` | `9ee940e944e929ac056ee0836d6f4050d2213625` | Executable repairs to network binding, safe-only, native input safety and engine/conservation boundaries. R.2.5 is the qualified executable baseline. |
| `codex/v1-1-fe110-readiness` | `629ada1264bb40796f2458ba7c5b948ccaa2e83c` | Three additions. Fe workflow completion report, evidence inventory and the V.1.1 history-event file. |
| `codex/v1-2-1-chco-thermochemistry` | `6dbc0fb35223cc832abc2fc19bc0ca6de54f4411` | Three additions. CHCO completion report, candidate inventory and the V.1.2.1 history-event file. |

**Change classification.** From the production comparator to R.2.5, the executable diff contains nine files under `scripts/`. These are `kinetic_data/native_rate_output.py`, `kinetic_data/network_binding.py`, `kinetic_data/stoichiometric_sources.py`, `multiphase_contracts.py`, `native_model.py`, `rate_output_v2.py`, `reaction_network/builder.py`, `state_manager/cli.py` and `surface_kmc/oxide_control.py`. Eleven test files, including `conftest.py`, and `pyproject.toml` supply test and gating changes. The remaining diff consists of project instructions, module references, five handoff event records, repair reports, readiness projections and the separately stored corrected R.2.3 native input bundle plus its Git attributes. There are zero changes to `tests/fixtures/` or the pre-existing native archives in that diff.

Each V.1 diff adds its evidence index, report and event under `reports/workflow_readiness/` and `modules/state_handoff/events/`. Neither changes executable code, tests, input fixtures or original scientific output files. A historical event file records a proposal at its existing review state.

**Development decision.** The last row supplies R.2 runtime behavior and both Fe inventories without transferring changes between refs. F1.1 uses a new worktree and a descendant report-only branch, `codex/f1-1-input-template-inventory`. The existing development and publication worktrees remain separate. F1.1 performed no branch integration, history rewrite or production publication.

To reproduce the comparison, resolve the four remote heads above, check ancestry in the displayed order, then run `git diff --name-status EARLIER LATER` for each adjacent pair. An identical source tree under `scripts/` across the two V.1 steps does not imply identical evidence inventories.
