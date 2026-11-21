# Stoichiometric sources on a native rate basis

Use `scripts.kinetic_data.stoichiometric_sources` for signed production of molecules and vacant sites. Pass reaction definitions and qualified net progress at the same operating condition, with the same denominator and time unit. The V2 envelope owns unit, version, directional and provenance checks. The original `scripts.rate_output_v2.generate_source_terms` import resolves to the shared function. Neither mathematical entry point grants scientific acceptance.

## Matrices and missing observations

`build_matrices(reactions)` returns sorted reaction IDs and two sparse dictionaries. Each outer key identifies a species or site inventory. Inner keys identify reactions. Species coefficients are products minus reactants. Vacancy coefficients are sites released minus sites consumed. The current reaction contract admits positive integral counts on each side. Subtraction can yield negative, zero or positive coefficients.

`project_progress(matrices, net_by_reaction_id)` returns two signed rate dictionaries. For a matrix row, multiply each nonzero coefficient by the corresponding net progress and sum the contributions. A zero is an observed value. An unknown net makes exactly the dependent rows unknown. A spectator present equally on both sides retains an explicit zero source. A site or species absent from every definition has no row. Inventories retain their project IDs across surfaces, interfaces and phases.

For validated V2 input, `not_applicable` excludes one direction. A missing directional observation remains unknown. A numerical net with one or more unknown directions must meet the envelope's existing `net_evidence` and consistency rules. The low-level projection accepts qualified net rates directly and has no authority to validate provenance.

## Conservation and source residuals

`conservation_residuals(matrices, species_records)` returns exact integer residuals per reaction. Each element sums its atom counts times species coefficients. Charge uses the same coefficients and declared species charges. Each inventory sums its vacancy coefficient and changes in occupied sites, using each species' own footprint on that inventory. A zero in all applicable cells establishes stoichiometric conservation. Nonzero cells identify the reaction and failed balance. Missing composition, charge or footprint on a changing species prevents certification and identifies the missing input. Known empty footprints are valid for unbound species.

`source_residuals(expected, reported)` compares two sets of projected or measured source rows by ID. The signed residual is reported minus projected. Agreement uses the existing relative tolerance of 1e-12 with zero absolute floor. A known/unknown mismatch is inconsistent. Two unavailable values have a null residual and matching availability. Element conservation, site conservation, numerical agreement and kinetic eligibility answer separate questions.

## Optional covariance

`source_covariance(matrices, native_normalization, covariance=C, reaction_ids=ids)` takes the parent V2 normalization record and a full finite, symmetric net-progress covariance, with the declared reaction order on both axes. The result labels every species and vacancy axis. Each covariance entry has the product of its two axis units, including both native denominators and time factors. For event counts the numerators are molecule and vacancy counts. For molar progress, the parent amount unit applies to each axis.

The calculation is `N C Nᵀ` with species and vacancy rows stacked. Positive-semidefinite singular inputs are supported. The finite-precision PSD check uses dimensionless correlations, with an explicit check against negative propagated variance. An incoherent covariance, duplicate axis label or mismatched reaction set is an input error.

Use `independent_variances={reaction_id: variance, ...}` only when independence has been established. A null variance makes entries depending on it unavailable. If the covariance and the independence evidence are both missing, omit both arguments and the returned covariance is null. Rate-coefficient uncertainty and activation-energy uncertainty alone cannot establish net-progress uncertainty. Pass qualified uncertainty on the native basis. Wire schemas and their provenance rules retain their existing versions.
