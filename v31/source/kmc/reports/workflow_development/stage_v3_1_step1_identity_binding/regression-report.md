# Step 1 offline regression and evidence review

| Worktree | Collected | Passed | Skipped | Failures/errors | Ruff on task files |
|---|---:|---:|---:|---:|---|
| codex/mkm-v244 | 287 | 286 | 1 | 0 | Passed |
| codex/kmc-v300 | 222 | 222 | 0 | 0 | Passed |

The only skip was `test_live_closed_cycle`, which requires an explicitly reviewed CATKINAS run and decision. Both test processes were started in their own worktree with independent Python imports. Native-format fixture tests used existing test doubles or replayed files. The three example-sidecar verification calls read completed synthetic-benchmark evidence from disk. Native solver starts during this task were zero. Raw case names, outcomes and times are in [MKM JUnit](m-pytest.xml) and [KMC JUnit](k-pytest.xml).

## What the new tests establish

- Reordered species/catalog records retain identity. A balanced dissociative event and balanced dimer event with the same two vacancies fail the molecular gate. A conserved additional vacancy requirement fails the separate site gate. Stale versions, unknown IDs, altered site owners, impossible footprints, contradictory reverse records, missing patterns and changed spectators are rejected.
- Parameter sets sharing a label can carry different energy references and uncertainties. Whole-row hashes preserve the original rates, their units and source metadata. This layer does not certify synthetic uncertainty values as physical measurements.
- Two synthetic MKM executions reach identical endpoint vectors from different starts. Their root-state digests coincide while their point bindings differ. Changed root, conditions, execution sidecar and whitespace-only input file changes fail. The historical point can be replayed with an explicitly attributed legacy normalization profile.
- Two equal-valued KMC windows inside one holding interval have distinct evidence digests. A three-segment fixture retains each checkpoint writer. A changed restart file, altered binding, and an out-of-range window fail. The pre-existing trajectory, continuation, topology, kinetic adapter and V2 format regressions ran alongside these tests.
- Both worktrees also read the two actual reviewed datasets from disk and independently rejected `ads` with the diagnostics `molecular_stoichiometry, local_geometry`. The second archived KMC example reconstructs the original three segments ending at events 7, 13 and 24.

## Reproduction

The commands below reproduce the selected offline suites, lint and archived-sidecar verification. The new test modules and exact source delta are included in the per-worktree patches. The two JUnit destinations are output files.

### MKM worktree

```powershell
Set-Location -LiteralPath 'C:/Users/86177/Desktop/sbq123-mkm-v244'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
@'
import sys
from pathlib import Path
import pytest

def offline(event, args):
    if event == "subprocess.Popen":
        program = Path(str(args[0])).name.lower()
        if any(name in program for name in ("matlab", "catkinas", "zacros")):
            raise RuntimeError("Native solver dispatch blocked during offline regression")

sys.addaudithook(offline)
sys.exit(pytest.main(sys.argv[1:]))
'@ | C:/Anaconda/python.exe -B - -p no:cacheprovider -q --tb=short tests/test_scientific_identity.py tests/test_mkm_result_binding.py tests/test_mkm_single_point.py tests/test_mkm_steady_states.py tests/test_mkm_normalization.py tests/test_mkm_general_mapping.py tests/test_rate_output_v2.py tests/test_kinetic_parameters.py tests/test_native_model.py --junitxml='C:/Users/86177/Desktop/sbq123-kmc-v300/reports/workflow_development/stage_v3_1_step1_identity_binding/m-pytest.xml'
C:/Anaconda/python.exe -B -m ruff check --no-cache scripts/kinetic_data/scientific_identity.py scripts/baseline_mkm/result_binding.py tests/test_scientific_identity.py tests/test_mkm_result_binding.py
C:/Anaconda/python.exe -B -m scripts.baseline_mkm.result_binding reports/workflow_development/stage_v2_4_4_step3/nicu-400k-001 --verify 'C:/Users/86177/Desktop/sbq123-kmc-v300/reports/workflow_development/stage_v3_1_step1_identity_binding/mkm-point.json'
```

### KMC worktree

```powershell
Set-Location -LiteralPath 'C:/Users/86177/Desktop/sbq123-kmc-v300'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD='1'
@'
import sys
from pathlib import Path
import pytest

def offline(event, args):
    if event == "subprocess.Popen":
        program = Path(str(args[0])).name.lower()
        if any(name in program for name in ("matlab", "catkinas", "zacros")):
            raise RuntimeError("Native solver dispatch blocked during offline regression")

sys.addaudithook(offline)
sys.exit(pytest.main(sys.argv[1:]))
'@ | C:/Anaconda/python.exe -B - -p no:cacheprovider -q --tb=short tests/test_scientific_identity.py tests/test_kmc_result_binding.py tests/test_kmc_workflow.py tests/test_kmc_spatial_core.py tests/test_kmc_native_observations.py tests/test_kmc_seed_analysis.py tests/test_rate_output_v2.py tests/test_kinetic_parameters.py tests/test_native_model.py --junitxml='C:/Users/86177/Desktop/sbq123-kmc-v300/reports/workflow_development/stage_v3_1_step1_identity_binding/k-pytest.xml'
C:/Anaconda/python.exe -B -m ruff check --no-cache scripts/kinetic_data/scientific_identity.py scripts/surface_kmc/result_binding.py scripts/surface_kmc/study.py tests/test_scientific_identity.py tests/test_kmc_result_binding.py
C:/Anaconda/python.exe -B -m scripts.surface_kmc.result_binding reports/workflow_development/stage_v3_0_0_kmc_step3/09-long-periodic-3x3-seed-73411/dataset.json reports/workflow_development/stage_v3_0_0_kmc_step3/09-long-periodic-3x3-seed-73411/configuration.json reports/workflow_development/stage_v3_0_0_kmc_step3/run-09-long-periodic-3x3-seed-73411 0.05 1.55 --verify 'C:/Users/86177/Desktop/sbq123-kmc-v300/reports/workflow_development/stage_v3_1_step1_identity_binding/kmc-window-73411.json'
C:/Anaconda/python.exe -B -m scripts.surface_kmc.result_binding reports/workflow_development/stage_v3_0_0_kmc_step3/02-local-writer/dataset.json reports/workflow_development/stage_v3_0_0_kmc_step3/02-local-writer/configuration.json reports/workflow_development/stage_v3_0_0_kmc_step3/run-04-second-continuation 0 0.0001 --verify 'C:/Users/86177/Desktop/sbq123-kmc-v300/reports/workflow_development/stage_v3_1_step1_identity_binding/kmc-window-continuation.json'
```
