# Phase 3.2.1 bounded batch approval plan

The accepted synthetic Ni/Cu closed cycle uses 400 K, 1.0 bar H₂, 0.5 bar NO and 0.1 bar HNO. Its baseline overall TOF is 81.51277016 turnovers per reference pair (one Ni-top and one Cu-bridge site) per second. Network version `0978e2199dd35b1bae883edcfb6537376c3152d13fa1f54a4102cc4f035d8264`, kinetic dataset `417cf1dc3236175476441c4c4e7b4bd5771bc4a7062aa5e34eff69070483d11b`. The batch plan binds the baseline source files, published results and individual member plans. [Immutable approval plan](batch-plan.json)

| Reaction | Reviewed TS | Forward / reverse Gibbs barriers (eV) | Plan |
|---|---|---:|---|
| ads | fixture-ts-ads, synthetic Grade A | 0.400 / 0.500 | One ±0.005 eV pair |
| transfer | fixture-ts-transfer, synthetic Grade A | 0.760 / 0.740 | Reuse verified 0.010 and 0.005 eV pairs |
| hydrogenate | fixture-ts-hydrogenate, synthetic Grade A | 0.780 / 0.880 | Reuse verified 0.010 and 0.005 eV pairs |
| desorb | fixture-ts-desorb, synthetic Grade A | 0.800 / 0.740 | One ±0.005 eV pair |

Both displacements change the selected forward and reverse activation energies by the same signed amount at fixed endpoint energies, prefactors, pressure orders and reaction free energy. In desorption the reverse coefficient has units bar⁻¹ s⁻¹. In adsorption the forward coefficient has those units. Its reviewed law uses dissociative capture and the reverse rate follows equilibrium. At 400 K the exporter encodes the prefactor into an apparent native forward barrier of 0.7853168271 eV at baseline and 0.7903168271 / 0.7803168271 eV for the two signed inputs. Those inputs represent the reviewed 0.400 ± 0.005 eV physical barrier. Both exported directional coefficients change by the prescribed Boltzmann factor. [Rate-law and native-input audit](kinetic_review.json)

| Order | Reaction | TS shift (eV) | Single-point plan SHA-256 |
|---:|---|---:|---|
| 1 | ads | +0.005 | `54a3267854cc87a0fd7401ccca8d7448a4c7f33c662ac83d99fb0e2a8b0aac1a` |
| 2 | ads | −0.005 | `f882f1693190f9b01f7f2f5025fdf31b2f2516251ae3101c3ff6a0abb10d50f5` |
| 3 | desorb | +0.005 | `2359227137e0adc57c888a9550a0abf8105b1861b69754abeead2528df90e466` |
| 4 | desorb | −0.005 | `c9fc3cbab432e9e677be584ce396b1b0d4cae22d5e06e9ac24b3155fea61aabe` |

Batch SHA-256 (canonical JSON): `3d524ac8ec197637e808831d013cd94bb874509dcd81110391ae607423a3d70b`. All four single-point decisions must pass preflight before the first launch. At most one process runs at a time, with a 210 s per-run limit, 840 s total native allowance and 960 s batch wall-clock budget. A failed member stops subsequent launches with zero retries. Each new complete pair supplies one central estimate and two one-sided estimates. A second reviewed step size is needed to establish stability for a newly sampled reaction.

The real Fe(110) network lacks reviewed reversible kinetics and compatible endpoint thermochemistry. Its scope check yields zero planned runs and an unavailable DRC. [Machine-readable exclusions](fe110_exclusion.json)
