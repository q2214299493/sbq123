# Scientific basis of the synthetic pilot

The reviewed Ni/Cu model fixes the vacancies of both site inventories at zero formation Gibbs energy, and uses gas H₂ and NO as its composition references at 400 K. Its source supplies formation Gibbs energies for all six species and absolute Gibbs energies for all four transition states. Separate electronic, vibrational and thermal contributions to each species formation value are unavailable in this synthetic fixture. [Species, source hash and Fe exclusion](eligibility.json)

## Surface intermediate

The selected HNO-top occupies one Ni-top site on facet-Ni (fcc-Ni) and has reviewed formation Gibbs energy −0.140 eV on demo-ref at demo-standard. The other eligible surface intermediates, H2-top and H2-bridge, remain at their original energies. Changing HNO-top by a signed displacement h makes the following changes at fixed absolute transition-state energy.

| Reaction | Absolute TS (eV) | Reaction Gibbs energy (eV) | Forward barrier (eV) | Reverse barrier (eV) |
|---|---:|---:|---:|---:|
| hydrogenate | 0.740 | −0.100 + h | 0.780 | 0.880 − h |
| desorb | 0.660 | 0.060 − h | 0.800 − h | 0.740 |

Adsorption and transfer have no HNO-top participant. Their parameters and both endpoint energies are unchanged. Surface sensitivity uses **+kBT** times the central log-TOF slope per eV; the existing TS DRC convention uses a negative sign for a displaced transition state.

## Gas feed

The accepted feed at 400 K is H₂ 1.0 bar, NO 0.5 bar, HNO 0.1 bar. Every kinetic parameter set has a reviewed total-pressure range of 0.9–1.6 bar. NO is first order in the forward elementary hydrogenation law and zero order in its reverse law. None of the other three elementary laws contains NO explicitly.

At fixed other partial pressures the positive branch starting at 1.6 bar exceeds the reviewed range for any positive NO displacement. The engine checks that bound before execution. A distinct, isobaric composition experiment scales NO by exp(±ε), then distributes the remaining pressure between H₂ and HNO in their original 10:1 ratio. Its log-TOF slope includes the response to those compensating changes in addition to the response to NO. A fixed-other-pressure NO order requires new pressure applicability evidence or a separately accepted baseline inside the valid range.
