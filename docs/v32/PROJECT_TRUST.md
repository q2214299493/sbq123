# Project scientific approvals

The deploying operator supplies an absolute `SBQ123_PROJECT_TRUST_STORE` path and a separately retained lowercase `SBQ123_PROJECT_TRUST_SHA256` for its exact bytes. The service operator controls the environment and filesystem. Sending a digest inside a scientific request grants no approval. Anyone who controls the service environment controls its trust anchor. SHA-256 authenticates bytes against that anchor; it does not identify or sign for a human reviewer.

The JSON format is `sbq123-project-trust/1`. It requires a nonempty project name and records with a unique ID per kind, a lowercase SHA-256, decision `approved`, reviewer and an ISO timestamp with timezone. For documents supply a path under the store directory. The loader rejects mismatched bytes, ambiguous keys and paths resolving outside that directory. Built-in registry IDs take precedence. To revoke approval the operator deploys a replacement store and its independently authorized digest. An absent store permits built-in controls. A partially configured or changed store fails the requested project lookup.

| Kind | Meaning of the record digest and selection |
|---|---|
| datasets | File containing model, canonical model SHA-256 and evidence scope. Chemical formulae, conservation, domain, positive rates, physical basis and site inventory follow the existing model schema. Direct Model.from_record validation alone produces user-supplied provenance. |
| network_model | File with scope reviewed_project, use_scope project, and network and kinetic_dataset references. Each reference carries a project ID and exact source SHA-256. Each source also has its own document record. Coefficients converted at a single state remain scoped to that state. |
| thermo_companion | File with the same dataset ID, binding the model digest, thermodynamic species, elemental weights and any applicable site geometry. Only the Cantera operation needs this input. |
| catalysts, basis_conversions | Independent scientific registry records. The site-density conversion must match the model, selected catalyst and physical basis. |
| rate_review | File keyed by the original rate-output file SHA. It contains family (catkinas or zacros), scope reviewed_project and row from the producing replay contract, including output_sha256, dataset_id, network_version, dataset_version and original provenance references. The original rate file is checked separately. |
| mass_conversion, rate_mapping | Exact detached review file bytes. The owning reader checks the calibration or mapping, source, context, conditions and physical denominator. See the mass contract. |
| discovery_return | Exact detached scientific-return-review/1 file. Planning, owner review and any required execution authority have distinct roles. |
| reactor_result | Producer's canonical result_sha256. Both sides of a contrast need an independent identity and compatible operating conditions. The analyst's proposed digest alone permits reported-only inspection. |

## Run the manufactured user-model example

Use an installed Reactor environment. In PowerShell, from the source checkout, run the following commands. The example pin accompanies the source solely to reproduce this manufactured numerical control. Provision the production pin through the operator's independent review channel.

```powershell
$example = (Resolve-Path docs/v32/examples/project-trust).Path
$env:SBQ123_PROJECT_TRUST_STORE = Join-Path $example 'project.json'
$env:SBQ123_PROJECT_TRUST_SHA256 = (Get-Content (Join-Path $example 'operator.sha256') -Raw).Trim()
python -I -m sbq123.reactor (Join-Path $example 'cstr.json')
```

The isothermal first-order A to B control has k = 0.6 per second and a one-second residence time. Its analytical CSTR conversion is 0.375. Changes to the companion bytes prevent Reactor execution while leaving the valid kinetic model available to independent operations. This example has no physical catalyst qualification.
