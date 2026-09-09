---
document_class: CURRENT_REFERENCE
as_of: '2026-09-10T00:00:00+08:00'
as_of_scope: B7 software distribution review, not production observation
source_scope: B7 publication branch based on the B6 release
source_branch: codex/b7-release-environment
source_version: 93c09db8a6008a873ef7cc8bc7b4cc1e2a8cc22a
source_version_role: B7 base commit
evidence_kind: SOFTWARE_TEST_RECORD
production_schema_version: NOT_VERIFIED_IN_B6
---

# Installation and distribution contract

The development checkout remains `C:/Users/86177/Desktop/work`. Publication task
branches use the independent `q2214299493/sbq123` history and carry only reviewed
source changes. A wheel provides software and enumerated non-sensitive resources;
it is not a project backup or an HPC deployment.

## Normal installation

Python 3.11 is the required Linux/Windows CI reference. Python 3.13 is additionally
exercised on the local Windows host; this does not extend every scientific extra's
platform support. The declared minimum remains Python 3.11.

```text
python -m venv /path/to/new/environment
/path/to/environment/python -m pip install /path/to/sbq_catalyst_agent_workflow-0.1.0-py3-none-any.whl
```

On Windows the interpreter is `environment/Scripts/python.exe`; on Linux it is
`environment/bin/python`. Run installed commands from any working directory:

```text
registry-write --help
registry-init --help
ts-strategy --help
catalysis-search --help
catalysis-validate --help
repo-state --help
registry-promote --help
document-governance --help
capability-readiness --help
python -m scripts.release_smoke
```

Registry initialization and writes require an explicit local `--db` path in a
wheel installation. TS scientific operations require their existing explicit
input/evidence/database arguments and the appropriate extras. Defaults for
reviewed policies resolve through `scripts.runtime_resources.resource_path`, not
the current working directory. Existing Python `-m scripts...` APIs remain usable.

## Developer checkout

```text
python -m pip install -e ".[dev,neb,release]"
python -m ruff check scripts modules tests
python -m pytest -o addopts= -q
```

On supported Linux environments add `sella` to run the existing CPU analytical
Sella tests. Scientific thresholds, backend roles and acceptance gates are not
changed by an installation mode.

## Capability and dependency boundaries

| Capability | Contract | Dependencies / context |
|---|---|---|
| Registry plan/apply, initialization/migration | Package-supported with explicit DB | CORE_REQUIRED: jsonschema, NumPy, PyYAML; SQLite from Python. No production DB supplied. |
| TS CLI help, pure contract/decision tools | Package-supported | Core; element-labelled contracts use `vasp` extra. |
| NEB/AdsMind geometry operations | Package-supported for explicit local inputs | OPTIONAL_EXTRA: `neb` or `adsmind` (ASE); VASP-backed structure interpretation may require `vasp` (pymatgen). |
| VASP INCAR/structure library integrations | OPTIONAL_EXTRA | `vasp`: pymatgen. The repository-owned parsers and scientific policies retain their existing ownership. |
| Retrieval CLI, whitelist/schema checks, precomputed embeddings | Package-supported | Core for record checks, explicit lexical diagnostics and reviewed precomputed-vector mode. |
| Online semantic encoder | OPTIONAL_EXTRA | `retrieval`: sentence-transformers; reviewed model cache is OPTIONAL_EXTERNAL_RESOURCE. No automatic weaker fallback. |
| Sella ML candidate refinement | OPTIONAL_EXTRA plus EXTERNAL_RUNTIME | `sella` plus `neb`; Linux/Python 3.11 CPU mock gate. Windows Sella and production GPU/vendor stacks are unverified. |
| Plotting | OPTIONAL_EXTRA | `visualization`: matplotlib. |
| Building/testing | OPTIONAL_EXTRA | `release`: build/wheel; `dev`: pytest/Ruff/pymatgen. Constraints are direct requirements; actual resolved versions are reported per environment. |
| State manager audit/sync, document/readiness CLI | REPOSITORY_ONLY_RESOURCE | Help works in wheel; operations require `--root` with the source documents/configuration/events. No runtime state is packaged. Missing context raises REPOSITORY_CONTEXT_REQUIRED. |
| Excel promotion | Repository-only reviewed workflow plus EXTERNAL_RUNTIME | Help works in wheel; workbook/review operations retain repository containment. Node.js and @oai/artifact-tool are explicit external dependencies. The JS adapter is packaged but no workbook or Node stack is included. |
| Campaign-specific scripts, skill procedures, historical module aliases | Repository-only | Existing reviewed calculation/workspace context and skill resources; not standalone installed capabilities. |
| VASP/VTST, AQCat25, MatRIS, schedulers | EXTERNAL_RUNTIME | Separate approved deployment, licenses, credentials and models. Installation grants no execution authority. |

The legacy retrieval skill file paths remain thin CLI/import facades. New installed
entrypoints own only argument parsing; record validation/ranking remain in the B5
owners. Standalone AQCat25 schema/handoff deployments retain explicit/sibling
schema handling without requiring a newly deployed packaging helper.

## Runtime resources and exclusions

The exact [release resource inventory](../configs/release_resources.json) names
all packaged configs, registry schema/migrations, retrieval references and shell/JS
or LSF templates. Setuptools copies these originals into wheel build output under
`scripts/_resources/`; there is no maintained second config copy. The resolver uses
`importlib.resources` for installed data, and explicit source paths for checkouts.

Documentation/module metadata/task history is repository-only. Scientific inputs,
calculation outputs, accepted results and model checkpoints remain external to the
wheel. No POTCAR, WAVECAR, CHGCAR, production SQLite, private keys, credentials,
private runtime output or full model weights are distributed. Installing this
package does not install VASP, remote scheduler access or HPC/GPU credentials.
The [B6 data policy](../configs/data_governance.yaml) remains the handling authority.

Generated egg-info/dist-info/cache metadata is excluded from new state-manager
classification proposals. Git already ignores egg-info/build/dist. Existing
immutable events retain their old hashes and can still require reconciliation;
they are never rewritten to conceal a stale metadata classification.

## Release gates

```text
python -m scripts.validate_release --source /path/to/reviewed/checkout --output /new/outside/directory
```

The validator exports only indexed/versioned files to a disposable clean source,
builds a real wheel with pip's PEP 517 builder, audits every wheel member, creates
two fresh virtual environments without system packages, and compares normal vs
editable installation outside the checkout. New source files must be indexed
before a local pre-commit release check. No private development runtime is copied.
The mock chain loads packaged policies, validates a synthetic contract, binds a
local evidence file, approves/applies a temporary registry plan, and checks
idempotency. It inserts no scientific result and performs zero external actions.

CI retains a full Linux scientific/mock suite, adds critical engineering tests on
Ubuntu/Windows Python 3.11, and runs actual wheel/editable parity on both platforms.
Environment JSON and logs are uploaded as SOFTWARE_ENVIRONMENT evidence, never
scientific reproducibility or production validation. Absolute paths in historical
reports retain their original historical scope.
