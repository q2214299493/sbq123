# RSI stable-entry repair —2026-11-14

## Outcome and scope

Explicit user authorization: change RSI to the stable entry and run protocol
preflight without model calls,so Codex version-directory changes do not repeat
the same startup failure. The operational profile is now:

`C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/daily_profile.json`

Its sole changed value is `codex`,now
`C:/Users/86177/AppData/Local/OpenAI/Codex/cli/codex.cmd`.
Model,effort,project/output roots,authentication-home location and RSI policies
are unchanged. No credentials,personal Codex config or native permission settings
were edited. No previous research run was resumed or relabeled successful.

## Root cause and actual code owner

The old profile named the removed WindowsApps26.1103.4239.0 executable. The
current installed application is26.1106.6628.0. Nov14 failed runs stopped at
admission with FileNotFoundError and zero model-turn starts/tool executions.
The Nov10 fix had changed a version-specific path,not the update-safe entry.

Actual RSI entry remains the existing `use_research.py` wrapper,which imports
`C:/Users/86177/Desktop/rsi-usage-dashboard-20261030/`. That source checkout owns
this repair. No duplicate research-assistant implementation was added to work.

Updated `scripts/ts_strategy_engine/review_app_server.py` resolves the modern
stable launcher on **every call**,without `shell=True` or cached native paths:

1. Check the recognized launcher layout and bounded text size.
2. Read only its `CODEX_CLI_PATH` setting from the existing user-profile config.
   A present target must be an absolute native codex.exe.
3. If that target is absent,permit only the launcher's exact unversioned
   `bin/codex.exe` fallback. Do not guess from retained version subdirectories.
4. Refuse an unknown modern layout or missing target with an explicit error.
   Preserve the existing older-launcher ambiguity guard.

The existing `LiveStdio` constructor still calls `verify_protocol` before
configuration/native-permission admission and before a model turn. No feature,
permission,source-access or scientific gate was removed or relaxed.

## Actual offline validation

Used the real resolver and owner `verify_protocol` with the existing isolated
authentication-home context. Five local commands exited0:

1. `--version`
2. `app-server --help`
3. `app-server generate-json-schema --help`
4. `features list`
5. `app-server generate-json-schema --experimental --out ...`

Required protocol fields,named filesystem permissions and disabled-feature
controls passed the existing owner validator. No app-server inference session,
thread/turn start,account/auth RPC,training,GPU or VASP task was started.

Resolved native CLI: `codex-cli 0.167.0-alpha.4.1`.
Binary SHA256:
`83f5c2dd2ac2902e0d96ba5d8ccdd27d513f57df4a9ab73e06a5a518028e9a2f`.
Runtime source SHA256:
`e7c4e14a252e320df292f61d8382d29a0b3879279e9464a0ae8926f216a8017e`.
Stable-entry SHA256:
`518c80cb397c332a28290ece4f3cc32e0f5c8fefd3293fb71b6009568c02cb4f`.

Profile before/backup SHA256:
`cdac1008d1670cd6f3be0758d2d4df8fc3beb20163c9e6ab0edf820bfe716202`.
Profile after SHA256:
`c0e6074c0d49335b888e87f6776fc9f2dc9050ee13cda87292bc534397bd31f2`.
Byte-level verification confirms only the one JSON codex string value changed;
the original backup is exact. Proposed and installed launcher/native/source
identities match the successful offline proof.

New `tests/test_rsi_stable_executable.py`:12 offline cases passed,covering
multiple retained versions,a changed target behind an unchanged entry,missing
target/fallback,absolute native-path requirements,changed/oversized layouts,
legacy ambiguity,direct-native behavior and PATH discovery. Related suites
`test_ts_next_review.py`,`test_research_assistant.py` and
`test_research_resume_cache.py` also passed. Syntax,scoped Ruff and diff checks
passed. These tests do not call a model.

## Evidence and remaining boundary

External runtime directory:
`C:/Users/86177/Desktop/fe110_rsi_experiments/rsi_runtime_policy_20261030/startup_preflight_stable_20261114_v1/`.
It retains each command receipt,generated schema,`offline_preflight.json` and
`installation_verification.json`. Original profile backup is
`daily_profile.before_stable_entry_20261114.json` beside the operational profile.
Runtime/profile/credential artifacts are not source-published.

This fixes version-bound startup and verifies offline protocol compatibility;
it does **not** prove live login,model entitlement,native-permission admission or
end-to-end research output. A future launcher/protocol redesign may still fail
explicitly;there is no promise of compatibility with arbitrary future versions.
On the next actual research request,use its original goal,budget and existing
admission checks. No extra model test or failed-study retry is authorized here.

Official interface reference: [Codex App Server](https://learn.chatgpt.com/docs/app-server).
OpenAI Docs was used to check the interface;actual local help/schema checks,
not a remote documentation version,determine this runtime's compatibility.
