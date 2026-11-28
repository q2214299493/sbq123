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
independent digest in an operator-approved `mass_conversion` record. Project deployment provisions the store path and a separately retained digest. The default deployment contains no project approvals. [Project trust contract](PROJECT_TRUST.md)

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

The original Windows files and their SHA-256 identities remain authoritative. Portable replay recomputes the dataset, checks its scientific inputs exactly, and compares only positive finite derived activity coefficients within four binary64 representable steps. The closed-cycle parent, the published synthetic interface dataset and four archived signed TS perturbations can recover their independently retained representations after this check. A failed comparison or altered source cannot establish approval.
