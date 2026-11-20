# Cross-reaction DRC comparison

Both synthetic reaction types meet the project step-size criterion on the same accepted Ni/Cu steady state at 400 K. Each row uses net overall turnover per reference site pair and a symmetric TS displacement at fixed endpoints, prefactors and gas pressures.

| Reaction | Step (eV) | Central DRC | Positive side | Negative side |
|---|---:|---:|---:|---:|
| transfer | 0.010 | 0.04113190545 | 0.04712912641 | 0.03513468449 |
| transfer | 0.005 | 0.04069045116 | 0.04367290219 | 0.03770800013 |
| hydrogenate | 0.010 | 0.45044071321 | 0.48009741200 | 0.42078401443 |
| hydrogenate | 0.005 | 0.45025755212 | 0.46510730761 | 0.43540779664 |

For transfer the absolute change is 0.00044145 against tolerance 0.00203452. For hydrogenate it is 0.00018316 against 0.02251288. The project uses the larger of 0.002 and 5% of the absolute fine-step DRC. The one-sided estimates retain measurable curvature for both reactions.

Transfer moves an adsorbate between Cu-bridge and Ni-top sites. Its forward flux is proportional to the occupied bridge fraction and top vacancy fraction. Its reverse flux uses occupied top and vacant bridge fractions. Both coefficients have units s⁻¹. Hydrogenate directly consumes gas-phase NO and a top-site adsorbate. Its forward flux contains NO pressure to power one and its reverse flux depends only on HNO-top coverage. [Rate laws and native flux replay](pressure_order.md)

At +0.005 eV for hydrogenate, H2-top coverage rises from 0.307101 to 0.326474, HNO-top falls from 0.401212 to 0.384417, and overall TOF falls from 81.51277 to 76.19477. At −0.005 eV the corresponding coverages are 0.288245 and 0.417813, and TOF rises to 86.82707. All four elementary net fluxes rebalance together. Adsorption and transfer each carry one event per turnover, hydrogenation and desorption each carry two. Under the same positive half-step for transfer, H2-top coverage changes to 0.305404 and the overall TOF to 80.99802. These comparisons describe the synthetic network at this one operating point.

The same reaction selector, signed-barrier transformation, native acceptance gate and central difference are used for both steps. The fine-pair comparison lists all coverage and elementary flux changes, site and elemental balance, steady-state and detailed-balance residuals by sign and step. [Step-size convergence report](fine/comparison.md) · [Machine-readable comparison](result.json)
