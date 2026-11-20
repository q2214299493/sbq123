# Sensitivity and reaction-order comparison

TOF is the positive net overall turnover per reference Ni/Cu site pair per second.
Baseline TOF: 81.51277016.

| Observable | Species | Step | Raised TOF | Lowered TOF | Central | Positive side | Negative side |
|---|---|---:|---:|---:|---:|---:|---:|
| intermediate_G-coarse | HNO-top | 0.01 | 90.6738723 | 71.8149381 | 0.401872339 | 0.367131318 | 0.436613361 |
| intermediate_G-fine | HNO-top | 0.005 | 86.181593 | 76.7084365 | 0.401377874 | 0.383967132 | 0.418788617 |
| gas_order-coarse | NO-g | 0.04 | — | — | unavailable | — | — |
| gas_order-fine | NO-g | 0.02 | — | — | unavailable | — | — |

## Step convergence

- intermediate_G: stable; absolute change 0.0004944650506277792, tolerance 0.020068893714043228.
- gas_order: unavailable; absolute change None, tolerance None.

## Coverage response

| Pair | Sign | Species | Coverage change |
|---|---|---|---:|
| intermediate_G-coarse | plus | H2-top | 0.0345146635 |
| intermediate_G-coarse | plus | HNO-top | -0.067296892 |
| intermediate_G-coarse | plus | H2-bridge | 0 |
| intermediate_G-coarse | minus | HNO-top | 0.0712396775 |
| intermediate_G-coarse | minus | H2-top | -0.0365368062 |
| intermediate_G-coarse | minus | H2-bridge | 0 |
| intermediate_G-fine | plus | HNO-top | -0.034296885 |
| intermediate_G-fine | plus | H2-top | 0.0175898977 |
| intermediate_G-fine | plus | H2-bridge | 0 |
| intermediate_G-fine | minus | HNO-top | 0.0352923393 |
| intermediate_G-fine | minus | H2-top | -0.0181004379 |
| intermediate_G-fine | minus | H2-bridge | 0 |

## Thermodynamic and pressure perturbations

- intermediate_G-coarse plus: G changes from -0.14 to -0.13 eV.
  - hydrogenate: reaction -0.09, forward 0.78, reverse 0.87, absolute TS 0.74 eV.
  - desorb: reaction 0.05, forward 0.79, reverse 0.74, absolute TS 0.66 eV.
- intermediate_G-coarse minus: G changes from -0.14 to -0.15 eV.
  - hydrogenate: reaction -0.11, forward 0.78, reverse 0.89, absolute TS 0.74 eV.
  - desorb: reaction 0.07, forward 0.81, reverse 0.74, absolute TS 0.66 eV.
- intermediate_G-fine plus: G changes from -0.14 to -0.135 eV.
  - hydrogenate: reaction -0.095, forward 0.78, reverse 0.875, absolute TS 0.74 eV.
  - desorb: reaction 0.055, forward 0.795, reverse 0.74, absolute TS 0.66 eV.
- intermediate_G-fine minus: G changes from -0.14 to -0.145 eV.
  - hydrogenate: reaction -0.105, forward 0.78, reverse 0.885, absolute TS 0.74 eV.
  - desorb: reaction 0.065, forward 0.805, reverse 0.74, absolute TS 0.66 eV.

Per-sign elementary pressure orders, forward and reverse fluxes, site balances and native detailed-balance residuals are stored with the corresponding case in [result.json](result.json).
