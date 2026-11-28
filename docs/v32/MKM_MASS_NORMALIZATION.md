# MKM mass-normalized turnover

MKM analysis always computes native observables with their original reference.
A mass rate under `tof.overall` or `tof.products` has units mol/(kg s), where
kg denotes total catalyst mass. The reference-pair count alone gives no
relationship to kg. A directly calibrated mol-reference/kg factor already
accounts for mass, so an absolute sample weight is unnecessary for this
intensive rate. A weight alone is insufficient.

## Evidence and calculation

Use the existing analysis options file to select a detached review using
`mass_conversion_approval` with `path` and `sha256`. Resolve its path relative
to the options file. The application checks its exact bytes against an
independent digest installed in `sbq123.common.evidence.trust.MKM_MASS_APPROVALS`.
The candidate ships with an empty set. A reviewed deployment may add a pin.

The review is a JSON object with format `mkm-mass-conversion/1`, decision
`approved`, a nonempty reviewer identity, the following context, and a
`calibration` file reference with path and SHA-256. Resolve that path relative
to the review file. The review authenticates the entire calibration file.

| Context field | Checked value |
| --- | --- |
| dataset_sha256, network_sha256, configuration_sha256, point_sha256 | Original input file byte hashes from the verified MKM calculation |
| catalyst_project_id, catalyst_catalog_sha256 | Network owner and canonical identity of its material, phase, surface and site catalog |
| reference_sha256 | Canonical identity of the entire verified native reference, including inventory, multiplicities, denominator magnitude and evidence |
| validity_scope | Scope of the bound result. The exact point and configuration further restrict the operating conditions |

The calibration file records `mass_basis="kg_total_catalyst"`,
`unit="mol_reference/kg"` and a finite positive numeric `value`. The independent
reviewer must establish the basis, value, units, catalyst and validity from the
calibration evidence before pinning. Each rate is the rate per one reviewed
reference per second multiplied by this factor.

An absent, altered, mismatched or unapproved record leaves the mass rate null.
The `mass_normalization` field reports status and reason, or the binding,
factor, approval and calibration digests when available. A caller-supplied
positive factor without a matching approval is retained only under
`hypothetical`. Multiplying a caller's site density by its specific surface area
cannot qualify a mass rate. Independent area and direct volume results retain
their existing conventions. Raw arithmetic helpers may be used in explicit
scenarios. Only the checked analysis entry qualifies a report.

## Consuming a saved analysis

Use `sbq123.common.evidence.mkm_mass.compare_mass_turnover(left, right)` in the
installed MKM environment for an overall mass-rate difference. Each side is
a pair of the deserialized report and keyword arguments for the original
`analyze` call. The reader replays the original inputs, verifies the detached
review and calibration, checks the saved report against the reproduced content,
and checks model, overall reaction and operating point before subtraction.
Unavailable inputs return a null difference with a reason. The existing six
MKM/KMC observables keep their original definitions and physical denominators.
Historical archived reports retain their recorded bytes and require fresh
analysis for a verified mass comparison.

## Archived replay portability

The 400 K closed-cycle source was retained from Windows. On the tested Debian
CPython 3.13.5 installation, rebuilding its kinetic dataset differs by one
binary64 ULP in each of three reverse coefficients. The resulting dataset
identity differs. Both the baseline and the correction reject this replay
before mass analysis. The portable tests exercise the calibration contract
separately and verify the rejection of this exact historical input. The
original public-entry controls run wherever the exact dataset reproduces.
