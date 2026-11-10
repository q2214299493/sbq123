# RSI startup-path repair — 2026-11-10

## Scope and actual change

User authorized correcting the launch path and a startup preflight only:
no research/model run, scientific job, authentication or permission change.

Only `codex` changed in the external operational configuration:
`C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/daily_profile.json`.
The missing `bin/22cfb1d302613eae/codex.exe` was replaced by the current
installed native binary:
`C:/Program Files/WindowsApps/OpenAI.Codex_26.1103.4239.0_x64__2p2nqsd0c76g0/app/resources/codex.exe`.
Model, effort, project/output roots, authentication directory and RSI policy
configuration are unchanged. The original profile bytes are retained beside
the configuration as `daily_profile.before_startup_fix_20261110.json`.

- Profile SHA256 before: `a48ad28bdf09aad3b463302ee3e3d1ec5c99eb385fb5313ed1f27e7eac41b677`.
- Profile SHA256 after: `cdac1008d1670cd6f3be0758d2d4df8fc3beb20163c9e6ab0edf820bfe716202`.
- Selected binary: `codex-cli 0.167.0-alpha.3.2`.
- Binary SHA256: `4b3286e35d7fe866c6b0eb3f07d7a4cdb5e96489576170dfd6b3a15aa1c67382`.

## Offline verification

The actual RSI executable resolver and existing `verify_protocol` implementation
were used from `C:/Users/86177/Desktop/rsi-usage-dashboard-20261030/`.
The resolver's existing `.cmd` handling assumes an obsolete versioned-bin
layout, so merely pointing the profile at the working Windows shim would not
be a reliable repair. No resolver or application files were modified.

An initial candidate using the unversioned native fallback was rejected: it
is version0.130.0-alpha.5 and `features list` cannot parse the existing named
filesystem permissions. Its four command receipts remain in
`startup_preflight_20261110_v1/`; permissions were not weakened to make it pass.

The selected current application binary passed all five actual offline checks:
version, app-server help, schema-generator help, feature inventory and local
experimental JSON-schema generation. Required protocol fields/permission
controls passed the owning validator. `use_research.py run --help` also exited0
before any research-run construction. The configured binary resolves to the
same binary/hash as the accepted offline proof. Parsed profile comparison
confirms exactly one changed key: `codex`.

Evidence is retained under the external runtime root:
`startup_preflight_20261110_v2/{protocol/,candidate_protocol.json,entry_help.json,verification.json}`.
These are operational checks, not scientific acceptance or training evidence.
The original failed research receipt is preserved unchanged as BLOCKED/NOT_RUN.

## Remaining boundary

- Zero research runs, model turns or scientific submissions were started.
- Live authentication, native-permission admission and inference were not tested;
  offline compatibility is not a claim that the full research workflow passed.
- The configured native binary is version-specific. An application update that
  removes it needs a new path/protocol check; no automatic updater was added.
- No task-owned runtime configuration, credentials or generated schema files
  are included in source publication; this document records the verified change.
- Final repository-state safe sync returned exit2 on the existing PKG-INFO
  classification conflict. No unchanged retry or managed-event bypass was made;
  this does not change the independent startup-preflight PASS.

Next:when a real research request is authorized, retain its original goal and
budgets and follow the existing full admission/resume path. Do not start one
merely to extend this offline preflight.
