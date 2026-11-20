# Pressure-order validation at 400 K

The accepted synthetic hydrogenation step is native CATKINAS equation 3, `H#1 + NO ⇌ HNO#1`. Its reviewed fixture TS is `fixture-ts-hydrogenate`, Grade A within the synthetic benchmark. Both activation Gibbs energies use `demo-ref` and `demo-standard` at 400 K. The forward and reverse baseline barriers are 0.78 and 0.88 eV. The common gas standard pressure is 1 bar.

| Direction | Native coefficient | Gas activity | Surface activity | Reconstructed flux |
|---|---|---|---|---|
| Forward | `kf`, bar⁻¹ s⁻¹ | NO to power 1, 0.5 bar | Coverage of `H2-top` (`Q1_H`) | `kf × P_NO × Q1_H` |
| Reverse | `kr`, s⁻¹ | Gas order 0, factor 1 | Coverage of `HNO-top` (`Q1_HNO`) | `kr × Q1_HNO` |

H₂ and HNO partial pressures are 1.0 and 0.1 bar. Both explicit vacancy factors for this step are 1. The exporter converts the reviewed forward prefactor from Pa⁻¹ s⁻¹ to a coefficient expressed per bar before generating the fixed-temperature CATKINAS energy input. The native input uses ThermoMode 0, BarrierMode −2 and ConsMode 0. Raising or lowering the TS shifts both barriers equally. The reaction energy remains −0.100 eV in all four inputs.

| TS shift (eV) | Forward barrier (eV) | Reverse barrier (eV) | Reconstructed forward flux | Reconstructed reverse flux | Overall net TOF |
|---:|---:|---:|---:|---:|---:|
| Baseline | 0.780 | 0.880 | 190.36328304 | 27.33774272 | 81.51277016 |
| +0.010 | 0.790 | 0.890 | 160.56708655 | 18.73776132 | 70.91466261 |
| −0.010 | 0.770 | 0.870 | 223.72645354 | 39.53388645 | 92.09628355 |
| +0.005 | 0.785 | 0.885 | 175.04609584 | 22.65654903 | 76.19477340 |
| −0.005 | 0.775 | 0.875 | 206.56716567 | 32.91302941 | 86.82706813 |

The directional columns are elementary events per reference site per second. The overall TOF is net HNO production divided by the overall HNO stoichiometric coefficient 2, in turnovers per reference Ni/Cu site pair per second. Replaying the four MAT files with native partial pressures and surface coverages reproduces both directional fluxes. The Ni-top and Cu-bridge inventory residuals and H/N/O elemental residuals are zero at recorded precision. The largest absolute native log detailed-balance residual across all four reactions is 3.341 × 10⁻⁶ or less, against the existing 10⁻⁴ tolerance. The largest surface steady-state residual is 1.422 × 10⁻¹³ or less.

The gas orders follow the reviewed rate law, input symbol mapping and replayed fluxes at the declared pressures. This phase did not measure a pressure-response curve. The archived cases include expected and native coefficients, activity orders and factors, the equation index, applied energy pair and source hashes. [Coarse pair](coarse/result.json) · [Fine pair](fine/result.json)
