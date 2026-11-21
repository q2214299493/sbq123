# Dimension-aware kinetic rate output 2.1.0

Use the existing offline V2 command. The dimensional revision needs the `rate-units` extra. With an explicitly supplied network, the CLI also verifies the raw network file SHA-256, its canonical version, the project and the declared inventory IDs against the site catalog.

```console
python -m pip install ".[rate-units]"
python -m scripts.rate_output_v2 output.json --network network.json
```

The document declares `"format": "kinetic-rate-output/2"` and `"schema_version": "2.1.0"`. Its network, conditions, reactions, embedded sources, provenance and validation use the established V2 definitions. A 2.0.0 document continues to use its original schema, input rules and CLI exit codes. Previous readers reject 2.1.0. No migration, fallback or rewrite is performed. [Original contract](multiphase_contracts.md) · [2.1.0 schema](../../configs/kinetics/rate_output_v2_1.schema.json)

## What a number measures

| Quantity | Representation and unit |
| --- | --- |
| Rate coefficient | Optional `rate_coefficients` rows reference a reaction. Each direction has its own value, original unit, rate-law ID, native reference description and activity orders. A Zacros coefficient can be per matching occurrence. The coefficient’s reference comes from that native law. |
| Forward / reverse flux | Nonnegative rates of reaction events on the declared time and physical denominator. Numeric zero, null (unobserved) and `not_applicable` (excluded direction) retain the V2 meanings. |
| Net progress | Signed event extent on the same basis. Incomplete directional observations require independent evidence for a known net. |
| Species source | Signed molecular count or amount of species, using net stoichiometry on the parent basis. |
| Site inventory source | Signed vacant-site count or amount of vacancies, independently for each inventory on the parent basis. |

A coefficient record can, for example, carry a value of 2 with unit `bar^-1 min^-1`, `rate_law_id="gas-adsorption"`, `native_reference="mean-field adsorption on the declared vacant-site population"` and `activity_orders={"pressure":1,"fractional_coverage":2}`. A direction with missing coefficient data may be null. Coefficients may be unreported even when event counts are available. Reaction IDs in the coefficient table must occur in the parent reaction rows.

For explicit pressure order p and concentration order c the required coefficient dimension is inverse time × pressure⁻ᵖ × (amount/volume)⁻ᶜ. Dimensionless activity and fractional coverage add no SI dimension, irrespective of their powers. Each power is a nonnegative integer in this revision. Zero-order coefficients have inverse-time units. Experimental laws outside this representation can retain their original parameter evidence and omit the coefficient block.

```python
from scripts.kinetic_parameters.rate_units import convert_coefficient, convert_unit

convert_unit(1, "atm", "Pa")  # 101325
convert_coefficient(60, "bar^-2 min^-1", "Pa^-2 s^-1", {"pressure": 2})  # 1e-10
```

Use space-separated products and at most one denominator product. Examples include `m^6 mol^-2 s^-1`, `L^2 mmol^-2 min^-1`, `cm²/g`, `mmol/L` and `1/(bar s)`. The unit backend handles pressure (Pa, kPa, bar, atm), time (ms, s, min, h), amount (mol, mmol), area, mass and volume. Event, molecule and vacancy count labels retain separate meanings. For a fixed quantity kind a count-to-mol request uses the Avogadro constant. Conversion between a pressure-based and a dimensionless-activity rate law would also require a standard-state model. `convert_coefficient` only changes units within the declared law.

## Native normalization and conversion evidence

Each 2.1.0 basis carries a `reference_scope` with the parent `project_id` and `network_version`, plus `basis_kind`, `reference_id`, `definition`, denominator magnitude and unit, extent unit and time unit. The three site-based kinds require unique `inventory_ids`. A site pair may use one inventory twice or span two inventories. `simulation_cell` names its physical cell. Known area, mass and volume bases require dimensionally compatible denominator units. A custom `other` basis needs its own unit label, definition and hash-bound `basis_evidence`. `unresolved` preserves the original label.

`convert_native_rate(value, quantity_kind, source_basis, target_basis, evidence=...)` returns the original value and basis alongside the requested basis, numerical result, evidence and status. Choose `forward_flux`, `reverse_flux`, `net_progress`, `species_source` or `site_source`. For count extents, the result labels the numerator as event, molecule or vacancy according to this choice. Denominator quantities such as “per 100 sites” are part of the arithmetic. Matching physical identities permit ordinary time, amount and display-unit conversion. Missing physical evidence gives `status="unavailable"`, `value=null` and the missing quantity. A structurally excluded direction gives `status="not_applicable"`.

| Physical relation | Evidence quantity | Canonical unit |
| --- | --- | --- |
| Individual reference sites per reference pair | `sites_per_reference` | 1 |
| Lattice sites per simulation cell | `lattice_sites_per_cell` | 1 |
| Lattice sites per reference site or pair | `lattice_sites_per_reference` | 1 |
| Reference sites or pairs per simulation cell | `references_per_cell` | 1 |
| Mole of specified reference units per catalyst area, mass or reactor volume | `reference_mol_per_catalyst_m2`, `reference_mol_per_kg`, `reference_mol_per_reactor_m3` | mol/m², mol/kg, mol/m³ |
| Catalyst surface area per mass or reactor volume | `catalyst_m2_per_kg`, `catalyst_m2_per_reactor_m3` | m²/kg, m²/m³ |
| Catalyst mass per reactor volume | `catalyst_kg_per_reactor_m3` | kg/m³ |

Each evidence record supplies the named positive value, unit, both physical reference hashes and a source artifact with path and SHA-256. `basis_identity` hashes kind, project/network scope, physical reference ID, definition and sorted inventory IDs. It includes supplied basis evidence and the original unit label for a custom or unresolved reference. Use the physical numerator and denominator in the table’s order even for reverse conversion. A mismatch of units, reference hashes or evidence quantity is rejected. Qualifying the cited measurement or model remains the researcher’s responsibility.

```python
from scripts.rate_output_v2 import basis_identity, convert_native_rate

# Both bases and the source artifact come from the project. density is in mol of this site's references per m².
proof = {
    "quantity": "reference_mol_per_catalyst_m2", "value": density, "unit": "mol/m²",
    "numerator_basis_sha256": basis_identity(site_basis),
    "denominator_basis_sha256": basis_identity(area_basis),
    "source": density_artifact,
}
report = convert_native_rate(native_source, "species_source", site_basis, area_basis, evidence=proof)
```

For a multi-step conversion, request each conversion in order and retain its evidence receipt. A site density cannot substitute for catalyst area per mass or for reactor loading. Independently supported direct ratios are also accepted. A coefficient per Zacros event embedding requires the event law and populations to produce flux. A shared SI coefficient unit, site label or converged solver alone cannot establish a mapping to a CATKINAS turnover. [Archived Ni/Cu reference investigation](../../reports/multiphase/stage_b1_1_audit/reference_site.md)
