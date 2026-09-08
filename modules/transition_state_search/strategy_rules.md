# Transition-State Strategy Rules

| Evidence | Strategy decision |
|---|---|
| endpoint or atom-map mismatch | stop; repair endpoints without interpolation |
| accepted exact Grade-A template | transfer its reviewed strategy |
| score above configured threshold | transfer strategy with human review |
| no accepted template | use deterministic family rule |
| collision, slab crossing, fixed-layer drift, or image jump | send evidence to the authoritative gate |
| physical internal minimum | optimize it and split the step once |
| decreasing force and valid geometry | evidence only; it cannot override a higher-priority failure |
| persistent plateau/oscillation | send force and geometry evidence to the gate |
| electronic failure | gate blocks production and permits only a preflighted diagnostic |
| smooth converged ordinary NEB with internal maximum | gate may authorize CI-NEB after all earlier checks pass |
| localized saddle-like image after valid CI-NEB | gate may authorize reviewed DIMER refinement |
| converged refined candidate | run frequency and connectivity validation |
| Grade-A validation | store as transferable successful template |
| failed or Grade-B/C validation | store failure reason and correction only |

Only `scripts/ts_strategy_engine/execution_gate.py` may authorize an action.
No table row, parser, monitor, or strategy helper is independently executable.
