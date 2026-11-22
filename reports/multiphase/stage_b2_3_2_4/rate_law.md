# Zacros 4.0 conventions for the synthetic CO2 control

For a **single ordered match** with one CO2 gas reactant, the adsorption propensity is `A_ads * P_bar * x_CO2 * exp(-Ea_ads/(kB*T))`. Desorption produces one gas molecule and its propensity is `A_des * exp(-Ea_des/(kB*T))`. Hence `A_ads=1.0e5 bar^-1 s^-1` and `A_des=1.0e13 s^-1` preserve the proposed numbers. The native reaction pattern supplies the number of distinct matches. Enter neither the two-match multiplicity nor a pre-applied gas pressure in the numeric prefactor. At fixed total pressure, halving the CO2 fraction halves only adsorption. This verification is for a gas coefficient of minus one.

| Quantity | Unit or interpretation | Evidence in the distributed 4.0 source and User Guide |
| --- | --- | --- |
| Gas pressure, mole fraction, temperature | bar, dimensionless, K. The native parser stores pressure as entered. | Guide pp. 20-21. `simulation_parser_module.F90` 1661-1670, 1691-1696, 1851-1858. |
| Gas stoichiometry and prefactor | A reactant with negative coefficient introduces a factor of total pressure times its fraction. A product introduces none. Constant prefactors enter as supplied. | `mechanism_parser_module.f90` 3324-3342, 3390-3394. Guide pp. 63-66. |
| Activation energy and clock | eV per elementary occurrence; propensity in inverse seconds. The source forms kB from R/NA in J/K and converts between J and eV. | `constants_module.f90` 77-94, 106, 117. `rates_handle_module.f90` 275-300, 577-592. |
| CO2 molecular weight | 44.0096 amu. Required for the gas declaration. The constant-prefactor law above contains no mass factor. | Guide p. 21. Distributed example 100, CO2 column in `simulation_input.dat`, SHA-256 `30de7fa0eae4d5646016796156efb57d2986fe5a1e3172cd9968fb04ac0d002f`. |
| Reference energies | Explicit CO2 gas energy 0 eV, both empty-site energies 0 eV. One occupied ordered bridge contributes -0.40 eV per molecule. | Guide pp. 21, 56-59. `mechanism_parser_module.f90` 3243-3281, 3309-3314 identifies the single-entity cluster by leg, type and adjacency, then combines with gas reference energies. |
| Cluster multiplicity and interactions | Multiplicity 1 for both empty sites and the ordered bridge. The two bridge legs share one entity label. The expansion has no multi-entity terms; their energy is explicitly zero. The declared proximity factor of 0.5 leaves the barrier unchanged because the coverage-dependent change in reaction energy is zero. | Guide p. 58. `rates_handle_module.f90` 575-592. The two-site cluster is a single-body energy term for one multidentate molecule. |
| Physical reversibility | The fixture has unknown physical reversibility. Two directed software probes enable separate catalogue checks. The 4.0 source emits warning 4008 for directed steps. This warning must be retained and reviewed, even if the other checks pass. | `mechanism_parser_module.f90` 858-869, 3587-3592. |

Each numeric choice is scoped to the synthetic dataset. Selecting -0.40 eV makes the reference energy difference consistent with the two requested barriers. The input contains no independently determined adsorption free energy or equilibrium constant. The detailed-balance verdict is `not_assessed`. At 400 K the release constants give kB = 8.617342430749591e-5 eV/K. [Values, ordered matches and analytical propensities](numerical_reference.json)

## Source identity

Distributed example 102 provides a native precedent for a single multidentate entity with ordered, typed sites and a single cluster energy. Its three-leg carbonate cluster has one entity ID on all three rows and graph multiplicity one. The accompanying general output confirms the energetics reader completed and the archived example terminated normally. The archived example's energies belong only to that example. Within the vendor ZIP, `examples/102/energetics_input.dat` hashes to `98d6c4df4d6839115795096e03ac7b5f6b2ae5e76a1887a43a2b543d7a6c0337` and `examples/102/general_output.txt` to `033b4d66110e50f369c58ab5aecd229563c78c66c46a81923f5d2beb3bb536c0`.

The installed [Zacros 4.0 distribution](https://zacros.org/software/obtain-zacros) was inspected offline. The local guide is dated 19 July 2024. The source files below are members under `zacros_4.0/` in the source ZIP. The binary identity matches previous successful archived runs; parser acceptance of the new model still needs its own native receipt.

| Object | SHA-256 |
| --- | --- |
| Distribution ZIP | `55ae665d845ad1120241b98e0a72192bb3737ade801275ec13c06d81fae9abae` |
| 4.0 guide | `cc64e35121f1637d3a371330882d2a53816bb15f0c3ee4d9b3b6fd4bd557f846` |
| Windows Zacros.exe | `84a8f88d6df633eeea9eeac8aa9227237cdf2564a4dc72e0cab8a18c4ce119d2` |
| constants_module.f90 | `dde2478a34a0228c59486327c9a360d095d63602433686ed7f2e6ad9f70b5bf1` |
| simulation_parser_module.F90 | `1ef07c6ae4b1bb4b816044ea12bdcc32b8e98d7c8fd5e14e4c3c8419a9ff7b3a` |
| mechanism_parser_module.f90 | `382bc2a137abcee6a799f3b0b392323bfc30c2d77f1ed0c5086344b4311927e0` |
| energetics_parser_module.f90 | `43f4216458bfa820c7be40c2e1176f70724d190654e80f4cc9c6379ebf17c911` |
| rates_handle_module.f90 | `90573ddcdf3939e006217f8f0b2ee629b03382c6ef474d52046b194fe1b696fa` |
