# Migration and compatibility

The baseline inventory verified the bytes of all 3,083 role assets and the Git blob identities of 2,296 tracked paths before migration. The frozen snapshot contains 22 differing same-name Python paths. The final V3.1 role inventories contain 23. The two sets have different membership. Both generations and both hashes per path appear in [role-variants.csv](audit/role-variants.csv).

| Inventory | Meaning |
|---|---|
| [Baseline ownership](audit/baseline-ownership.csv) | Every Git-tracked path in the release and its role classification or legacy designation |
| [Role assets](audit/role-assets.csv) | Per-role source and data locators, physical identity and ownership |
| [Baseline imports](audit/baseline-imports.csv) | Static Python import edges from the role sources and retained tests |
| [Canonical ownership](canonical-ownership.csv) | Each public runtime module's historical path and digest, role, and unique V3.2 physical source |

The 386 MKM and 390 KMC runtime Python entries map to 360 shared definitions, 26 MKM definitions and 30 KMC definitions. Each differing runtime implementation retains its own physical module. Role-specific historical tests remain in immutable V3.1 evidence and execute against the installed candidate. Shared legacy engine conventions remain available to both roles where the accepted inventories specified identical code. A distribution's role-specific files are exclusive to its own namespace.

Existing scientific Python imports can use `sbq123.common.compat.activate("mkm")` or `activate("kmc")` before importing a historical `scripts.*` module. The adapter resolves only the installed role inventory and rejects switching roles in a running process. A caller may use `python -I -m sbq123.common.legacy_cli ROLE MODULE [ARGS...]`. The nine historical console command names acquire an explicit `sbq123-mkm-` or `sbq123-kmc-` prefix. None installs a site-packages-root scripts package or a site startup hook.

Historical cases with source-relative data paths use `SBQ123_ROLE_DATA`. Prepare an explicitly selected case directory with `python -I tools/v32/prepare_history.py PATH_TO_V31 ROLE NEW_EXTERNAL_DIRECTORY` from an environment containing sbq123-common. The exporter pins the historical role index, hashes every selected asset, stages the directory on the destination volume, and publishes it atomically. It includes old test cases and small opt-in compatibility launchers. Preserve the recorded directory names mkm and kmc for paired archived runs. The installed runtime remains independent of the source checkout.

The historical negative test for a NaN geometry claim used its writer to construct a malformed record before invoking the verifier. V3.2 rejects NaN at the writer. The regression harness uses the V3.1 encoding **only in that test's malformed input constructor**, leaving its rejection assertions and the installed verifier intact. The independent strict-encoding test verifies that V3.2 cannot issue identities for NaN or infinity. The original frozen test files and JUnit evidence retain their V3.1 identities.

The sample paired replay in the acceptance bundle historically returns six insufficient-evidence comparisons because the KMC fixture's engine identity differs from the registered one. The V3.2 replay must preserve the returned values, reasons and uncertainty. It must also preserve the verified MKM counterpart. Other historical synthetic tests exercise reviewed window comparisons under their own fixture-specific authority.


The historical alternate-backend fixture now binds the exact test configuration digest through the operator approval setting before validation. That disposable binding is scoped to the single archived test.

The archived MKM timeout unit test supplies a wait-only fake PID. Its Windows replay adapts that object at the OS job boundary and uses a deterministic clock. The installed launcher and timeout implementation execute both original deadline assertions. Real child processes separately verify suspended launch, early parent exit and inherited-pipe cleanup.
