# MKM analysis · demo

Network `0978e2199dd35b1bae883edcfb6537376c3152d13fa1f54a4102cc4f035d8264`

synthetic_benchmark · 400 K · partial pressures in bar {"H2-g": 1.0, "HNO-g": 0.1, "NO-g": 0.5}

## Surface coverage

| Species | Phase | Surface | Site / type | Multiplicity | Species fraction | Occupied fraction | Fraction of all sites | mol/m² of surface |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| HNO-top | fcc-Ni | facet-Ni | top-Ni / atop | 1 | 0.401212208 | 0.401212208 | 0.200606104 | — |
| H2-top | fcc-Ni | facet-Ni | top-Ni / atop | 1 | 0.307101243 | 0.307101243 | 0.153550621 | — |
| H2-bridge | fcc-Cu | facet-Cu | bridge-Cu / bridge | 1 | 0.696679479 | 0.696679479 | 0.34833974 | — |

## Site utilization

| Site | Catalyst phase | Occupied | Vacant | Balance residual | Competitors by occupancy | Dominant |
| --- | --- | --- | --- | --- | --- | --- |
| top-Ni | fcc-Ni | 0.708313451 | 0.291686549 | 0 | ["HNO-top", "H2-top"] | ["HNO-top"] |
| bridge-Cu | fcc-Cu | 0.696679479 | 0.303320521 | 0 | ["H2-bridge"] | ["H2-bridge"] |

## Elementary rates

Directional and net flux units are events per reference site per second.

| Reaction | kf (unit) | kr (unit) | Forward flux | Reverse flux | Net flux | ΔG (eV) | ΔG‡ f / r (eV) | Near equilibrium |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ads | 1062.53345 (bar^-1 s^-1) | 58.3982074 (s^-1) | 94.0071328 | 12.4943627 | 81.5127702 | -0.1 | 0.4 / 0.5 | False |
| transfer | 2214.72714 (s^-1) | 3956.47883 (s^-1) | 450.059204 | 368.546434 | 81.5127702 | 0.02 | 0.76 / 0.74 | False |
| hydrogenate | 1239.74284 (bar^-1 s^-1) | 68.1378636 (s^-1) | 190.363283 | 27.3377427 | 163.02554 | -0.1 | 0.78 / 0.88 | False |
| desorb | 693.973663 (s^-1) | 3956.47883 (bar^-1 s^-1) | 278.430706 | 115.405166 | 163.02554 | 0.06 | 0.8 / 0.74 | False |

## Turnover and product distribution

Reference basis: reference_site_pair. Signed gas stoichiometry: {"H2-g": -1, "HNO-g": 2, "NO-g": -2}.

| Rate | Per reference/s | Per site/s | Per pair/s | mol/(m² s) | mol/(kg s) | mol/(m³ reactor s) |
| --- | --- | --- | --- | --- | --- | --- |
| Overall turnover | 81.5127702 | 40.7563851 | 81.5127702 | — | — | — |
| HNO-g | 163.02554 | 81.5127702 | 163.02554 | — | — | — |

Molar selectivity within the declared product set: {"HNO-g": 1.0}.
Element selectivity: {"C": null, "H": {"HNO-g": 1.0}, "N": {"HNO-g": 1.0}, "O": {"HNO-g": 1.0}}.
Net gas production: {"H2-g": -81.5127701616477, "HNO-g": 163.0255403232954, "NO-g": -163.0255403232954}.
Byproducts: —. Unconverted feed: —.

## Pathway graph

Directed species projection of stoichiometric hyperedges; simple species and reaction paths, 32 witnesses / 4096 expansions per feed-product pair. Components indicate mutual reachability. Feed closure requires all co-reactants, assumes site availability, and ignores flux magnitude. No atom tracing or flux decomposition.

- H2-g → HNO-g: ads (forward) → hydrogenate (forward) → desorb (forward), ads (forward) → transfer (forward) → hydrogenate (forward) → desorb (forward)
- NO-g → HNO-g: hydrogenate (forward) → desorb (forward)

Cross-phase reaction contexts: ["ads", "transfer"].
Mutually reachable components: [["H2-bridge", "H2-g", "H2-top", "HNO-g", "HNO-top", "NO-g"]].

## Scientific validation

Status: passed. Reconstructed maximum surface residual: 0.
Element balances: {"H": {"consumed": 163.0255403232954, "produced": 163.0255403232954, "residual": 0.0}, "N": {"consumed": 163.0255403232954, "produced": 163.0255403232954, "residual": 0.0}, "O": {"consumed": 163.0255403232954, "produced": 163.0255403232954, "residual": 0.0}}.
Missing quantities are marked —. Machine-readable activity factors, gas source terms, inventory-specific rankings and graph edges are in [analysis.json](analysis.json).
