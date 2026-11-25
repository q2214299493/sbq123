"""B.1.2 offline dimensional checks with independently specified factors and archived observations."""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.artifact_io import sha256_file
from scripts.kinetic_parameters.rate_units import convert_coefficient, convert_unit
from scripts.multiphase_contracts import validate_bundle
from scripts.rate_output_v2 import basis_identity, convert_native_rate, main, validate_rate_output_v2

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests/fixtures/multiphase/rate_output_v2.json"
ART = {"path": "synthetic/geometry.json", "sha256": "3" * 64}
LABELS = {"reference_site": "reference site", "reference_site_pair": "site pair", "lattice_site": "lattice site",
          "simulation_cell": "simulation cell", "surface_area": "m²", "catalyst_mass": "kg", "reactor_volume": "m³",
          "other": "named ensemble", "unresolved": "native slot"}


def basis(kind, **changes):
    result = dict(basis_kind=kind, denominator_unit=LABELS[kind], denominator_value=1, time_unit="s",
                  extent_unit="event", reference_id=kind, definition=f"Synthetic physical reference for {kind}",
                  reference_scope={"project_id": "synthetic-interface", "network_version": "b" * 64})
    if kind in ("reference_site", "lattice_site", "reference_site_pair"):
        result["inventory_ids"] = ["left", "right"] if kind == "reference_site_pair" else ["left"]
    if kind == "other":
        result["basis_evidence"] = ART
    return dict(result, **changes)


def evidence(quantity, value, unit, numerator, denominator):
    return dict(quantity=quantity, value=value, unit=unit, numerator_basis_sha256=basis_identity(numerator),
                denominator_basis_sha256=basis_identity(denominator), source=ART)


def document():
    doc = json.loads(FIX.read_bytes())
    doc.update(schema_version="2.1.0", native_normalization=basis("reference_site_pair"))
    return doc


@pytest.mark.parametrize("src,dst,factor", [
    ("Pa", "bar", 1e-5), ("atm", "kPa", 101.325), ("h", "s", 3600), ("s", "ms", 1000),
    ("min", "s", 60), ("mmol", "mol", .001), ("m²", "cm²", 10000), ("g", "kg", .001),
    ("m³", "L", 1000), ("mol/L", "mol/m³", 1000), ("fractional_coverage", "1", 1),
    ("dimensionless_activity", "1", 1), ("molecule/min", "molecule/s", 1/60),
])
def test_unit_scale_and_roundtrip(src, dst, factor):
    val = convert_unit(.25, src, dst)
    assert val == pytest.approx(.25 * factor)
    assert convert_unit(val, dst, src) == pytest.approx(.25)


@pytest.mark.parametrize("orders,src,dst,factor", [
    ({"dimensionless_activity": 1}, "min^-1", "s^-1", 1/60),
    ({"fractional_coverage": 3}, "ms^-1", "s^-1", 1000),
    ({"pressure": 1, "fractional_coverage": 2}, "bar^-1 s^-1", "Pa^-1 s^-1", 1e-5),
    ({"pressure": 2}, "bar^-2 min^-1", "Pa^-2 s^-1", 1e-10/60),
    ({"pressure": 4}, "atm^-4 h^-1", "kPa^-4 s^-1", 1/(101.325**4 * 3600)),
    ({"concentration": 1}, "L mol^-1 min^-1", "m^3 mol^-1 s^-1", .001/60),
    ({"concentration": 2}, "L^2 mmol^-2 min^-1", "m^6 mol^-2 s^-1", 1/60),
    ({"pressure": 1, "concentration": 1}, "L mol^-1 bar^-1 h^-1", "m^3 mol^-1 Pa^-1 s^-1", 1e-8/3600),
    ({}, "min^-1", "s^-1", 1/60),
])
def test_coefficient_uses_declared_orders(orders, src, dst, factor):
    value = convert_coefficient(3, src, dst, orders)
    assert value == pytest.approx(3 * factor, rel=1e-14, abs=0)
    assert convert_coefficient(value, dst, src, orders) == pytest.approx(3)


@pytest.mark.parametrize("src,dst,orders", [
    ("s^-1", "Pa^-1 s^-1", {"pressure": 1}), ("bar^-1 s^-1", "Pa^-2 s^-1", {"pressure": 2}),
    ("m^3 mol^-1 s^-1", "s^-1", {"dimensionless_activity": 2}), ("event/s", "s^-1", {}),
    ("event/s", "event/s", {}), ("s^-1", "s^-1", {"unknown": 1}), ("s^-1", "s^-1", {"pressure": -1}),
])
def test_dimension_or_law_mismatch_even_at_zero(src, dst, orders):
    with pytest.raises(ValueError):
        convert_coefficient(0, src, dst, orders)


@pytest.mark.parametrize("value,src,dst", [(1, "event", "molecule"), (1, "molecule", "vacancy"),
                         (1, "m²", "kg"), (.5, "fractional_coverage", "dimensionless_activity"),
                         (1.5, "fractional_coverage", "1"), (-1, "dimensionless_activity", "1"),
                         (float("nan"), "bar", "Pa"), (float("inf"), "g", "kg")])
def test_unit_conversion_rejects_wrong_kind_and_bad_numbers(value, src, dst):
    with pytest.raises(ValueError):
        convert_unit(value, src, dst)


@pytest.mark.parametrize("kind,label", [("forward_flux", "event"), ("reverse_flux", "event"),
                         ("net_progress", "event"), ("species_source", "molecule"), ("site_source", "vacancy")])
def test_native_source_semantics_and_weighted_denominator(kind, label):
    src = basis("surface_area", denominator_value=2, denominator_unit="cm²", time_unit="min")
    dst = dict(src, denominator_value=3, denominator_unit="m²", time_unit="s")
    original = deepcopy(src)
    result = convert_native_rate(4, kind, src, dst)
    assert result["value"] == pytest.approx(4 / 60 * 30000 / 2)
    assert result["native_numerator_unit"] == label and result["quantity_kind"] == kind
    assert result["native_value"] == 4 and result["native_basis"] == src == original
    assert convert_native_rate(result["value"], kind, dst, src)["value"] == pytest.approx(4)


@pytest.mark.parametrize("src_kind,dst_kind,quantity,unit,factor", [
    ("reference_site", "reference_site_pair", "sites_per_reference", "1", 2),
    ("lattice_site", "simulation_cell", "lattice_sites_per_cell", "1", 18),
    ("lattice_site", "reference_site_pair", "lattice_sites_per_reference", "1", 3),
    ("reference_site", "simulation_cell", "references_per_cell", "1", 7),
    ("surface_area", "catalyst_mass", "catalyst_m2_per_kg", "m²/kg", 135),
    ("catalyst_mass", "reactor_volume", "catalyst_kg_per_reactor_m3", "kg/m³", 250),
])
def test_explicit_bridge_or_exact_missing_quantity(src_kind, dst_kind, quantity, unit, factor):
    src, dst = basis(src_kind), basis(dst_kind)
    missing = convert_native_rate(-3, "net_progress", src, dst)
    assert missing["value"] is None and missing["status"] == "unavailable"
    assert missing["missing"] == [quantity] and missing["native_value"] == -3
    proof = evidence(quantity, factor, unit, src, dst)
    converted = convert_native_rate(-3, "net_progress", src, dst, evidence=proof)
    assert converted["value"] == pytest.approx(-3 * factor) and converted["evidence"] == proof
    assert convert_native_rate(converted["value"], "net_progress", dst, src, evidence=proof)["value"] == pytest.approx(-3)


def test_site_density_and_amount_are_independent():
    src, dst = basis("reference_site"), basis("surface_area", extent_unit="mmol")
    missing = convert_native_rate(2, "species_source", src, dst)
    assert missing["missing"] == ["reference_mol_per_catalyst_m2"]
    proof = evidence("reference_mol_per_catalyst_m2", 2, "mmol/m²", src, dst)
    assert convert_native_rate(2, "species_source", src, dst, evidence=proof)["value"] == pytest.approx(4)
    assert convert_native_rate(2, "species_source", src, dict(dst, extent_unit="event"), evidence=proof)["value"] == pytest.approx(
        4e-3 * 6.02214076e23)
    mol = dict(src, extent_unit="mol")
    assert convert_native_rate(6.02214076e23, "site_source", src, mol)["value"] == pytest.approx(1)


def test_conversion_chain_requires_each_applicable_factor():
    site, area, mass, volume = basis("reference_site"), basis("surface_area", extent_unit="mol"), basis("catalyst_mass",
        extent_unit="mol"), basis("reactor_volume", extent_unit="mol")
    density = evidence("reference_mol_per_catalyst_m2", .001, "mol/m²", site, area)
    specific_area = evidence("catalyst_m2_per_kg", 100, "cm²/g", area, mass)
    loading = evidence("catalyst_kg_per_reactor_m3", 2, "kg/L", mass, volume)
    areal = convert_native_rate(5, "species_source", site, area, evidence=density)["value"]
    per_mass = convert_native_rate(areal, "species_source", area, mass, evidence=specific_area)["value"]
    assert convert_native_rate(per_mass, "species_source", mass, volume, evidence=loading)["value"] == pytest.approx(100)
    assert convert_native_rate(areal, "species_source", area, mass)["missing"] == ["catalyst_m2_per_kg"]


@pytest.mark.parametrize("change", ["inventory", "reference", "direction", "unit", "source_hash", "quantity", "zero", "nan"])
def test_bad_or_misbound_evidence_rejected(change):
    site, area = basis("reference_site"), basis("surface_area")
    proof = evidence("reference_mol_per_catalyst_m2", .001, "mol/m²", site, area)
    if change == "inventory":
        site["inventory_ids"] = ["other"]
    elif change == "reference":
        area["reference_id"] = "other-area"
    elif change == "direction":
        proof["numerator_basis_sha256"] = basis_identity(area)
    elif change == "unit":
        proof["unit"] = "kg/m³"
    elif change == "source_hash":
        proof["source"] = {"path": "measurement", "sha256": "bad"}
    elif change == "quantity":
        proof["quantity"] = "sites_per_reference"
    else:
        proof["value"] = 0 if change == "zero" else float("nan")
    with pytest.raises(ValueError):
        convert_native_rate(1, "net_progress", site, area, evidence=proof)


@pytest.mark.parametrize("kind,bad", [("other", {"basis_evidence": None}), ("other", {"denominator_unit": "kg"}),
                         ("other", {"denominator_unit": "site pair"}), ("other", {"definition": ""}),
                         ("reference_site", {"denominator_unit": "reference site pair"}),
                         ("simulation_cell", {"denominator_unit": "lattice site"}),
                         ("reference_site_pair", {"inventory_ids": []}), ("catalyst_mass", {"denominator_unit": "L"}),
                         ("surface_area", {"time_unit": "Pa"}), ("reactor_volume", {"denominator_value": float("inf")})])
def test_invalid_native_normalization(kind, bad):
    p = document()
    p["native_normalization"] = basis(kind, **bad)
    with pytest.raises(ValueError):
        validate_rate_output_v2(p)


def test_unresolved_and_custom_denominators():
    custom = basis("other")
    assert convert_native_rate(0, "net_progress", custom, custom)["value"] == 0
    for src in (custom, basis("unresolved"), basis("surface_area", reference_id="unrelated")):
        report = convert_native_rate(4, "net_progress", src, basis("surface_area"))
        assert report["status"] == "unavailable" and report["value"] is None and report["native_value"] == 4


@pytest.mark.parametrize("kind,value,status", [("forward_flux", None, "unavailable"),
                         ("reverse_flux", "not_applicable", "not_applicable"), ("net_progress", None, "unavailable")])
def test_unknown_and_inapplicable_are_not_zero(kind, value, status):
    src = basis("reference_site")
    result = convert_native_rate(value, kind, src, src)
    assert result["status"] == status and result["value"] is None and result["native_value"] == value


@pytest.mark.parametrize("value,kind", [(-1, "forward_flux"), ("not_applicable", "species_source"),
                         (float("nan"), "site_source"), (0, "coefficient")])
def test_invalid_rate(value, kind):
    src = basis("reference_site")
    with pytest.raises(ValueError):
        convert_native_rate(value, kind, src, src)


def test_contract_revision_and_direction_binding(tmp_path):
    p = document()
    coeff = {"rate_law_id": "pressure-law", "value": 2, "unit": "bar^-1 min^-1", "activity_orders": {"pressure": 1},
             "native_reference": "Mean-field coefficient evaluated with gas partial pressure and vacant site fractions"}
    p["rate_coefficients"] = [{"reaction_id": "dissociate", "forward": coeff, "reverse": None}]
    before = deepcopy(p)
    validate_rate_output_v2(p)
    assert p == before
    path = tmp_path / "rates.json"
    path.write_text(json.dumps(p), encoding="utf8")
    assert main([str(path)]) == main([str(FIX)]) == 0
    for version in (None, "1.0.0", "2.0.0", "2.0.1", "2.1.1"):
        with pytest.raises(ValueError):
            validate_rate_output_v2(dict(p, schema_version=version))
    with pytest.raises(ValueError):
        validate_bundle(p)
    with pytest.raises(ValueError):
        validate_rate_output_v2(json.loads((FIX.parent / "valid.json").read_bytes()))
    Draft202012Validator.check_schema(json.loads((ROOT / "configs/kinetics/rate_output_v2_1.schema.json").read_bytes()))
    for bad in (dict(coeff, unit="event/s"), dict(coeff, extraneous=0), dict(coeff, value=float("nan")),
                {k: v for k, v in coeff.items() if k != "native_reference"}):
        p["rate_coefficients"][0]["forward"] = bad
        with pytest.raises(ValueError):
            validate_rate_output_v2(p)
    p["rate_coefficients"][0].update(forward=coeff, reaction_id="unbound")
    with pytest.raises(ValueError, match="matching reaction"):
        validate_rate_output_v2(p)
    p["rate_coefficients"][0].update(reaction_id="dissociate", forward="not_applicable")
    with pytest.raises(ValueError, match="excluded"):
        validate_rate_output_v2(p)


def test_scoped_network_catalog_and_raw_hash(tmp_path, capsys):
    archive = ROOT / "reports/multiphase/phase3_0/closed_cycle_network.json"
    network = json.loads(archive.read_bytes())
    p = document()
    p.update(project_id=network["project_id"], network_version=network["network_version"])
    b = p["native_normalization"]
    b.update(inventory_ids=["top-Ni", "bridge-Cu"], reference_scope={k: p[k] for k in ("project_id", "network_version")})
    # Map the synthetic test inventory IDs to real catalog IDs for a scoped catalog check.
    names = {"alpha": "top-Ni", "beta": "bridge-Cu"}
    for row in p["reaction_rates"]:
        for side in ("sites_consumed", "sites_released"):
            row[side] = {names[k]: v for k, v in row[side].items()}
    for row in p["source_terms"]["site_inventories"]:
        row["site_id"] = names[row["site_id"]]
    p["provenance"]["network"]["sha256"] = sha256_file(archive)
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(p), encoding="utf8")
    assert main([str(path), "--network", str(archive)]) == 0
    p["provenance"]["network"]["sha256"] = "a" * 64
    path.write_text(json.dumps(p), encoding="utf8")
    with pytest.raises(SystemExit) as exc:
        main([str(path), "--network", str(archive)])
    assert exc.value.code == 1 and "Network artifact SHA-256" in capsys.readouterr().err
    with pytest.raises(ValueError, match="digest"):
        validate_rate_output_v2(p, network=dict(network, altered=True))
    b["inventory_ids"] = ["top-Ni", "ghost"]
    with pytest.raises(ValueError, match="Unknown site inventories"):
        validate_rate_output_v2(p, network=network)
    b["reference_scope"]["project_id"] = "unrelated-project"
    with pytest.raises(ValueError, match="reference scope"):
        validate_rate_output_v2(p)


def test_same_display_name_does_not_bind_a_different_model():
    src = basis("reference_site")
    other = dict(src, reference_scope=dict(src["reference_scope"], project_id="second-project"))
    assert basis_identity(src) != basis_identity(other)
    assert convert_native_rate(1, "net_progress", src, other)["status"] == "unavailable"


def test_legacy_time_label_stays_opaque_and_legacy_needs_no_unit_backend(monkeypatch):
    from scripts.kinetic_parameters import rate_units

    def absent():
        raise RuntimeError("test: units backend unavailable")
    monkeypatch.setattr(rate_units, "_units", absent)
    old = json.loads(FIX.read_bytes())
    old["native_normalization"]["time_unit"] = "engine-native clock"
    validate_rate_output_v2(old)


def test_real_archived_coefficients_and_separate_engine_bases():
    root = ROOT / "reports/multiphase"

    def read(path):
        return json.loads((root / path).read_bytes())

    mkm = read("phase2_4/synthetic_interface_catkinas.json")
    kmc = read("phase2_4/synthetic_interface_zacros.json")
    assert "per reference site" in mkm["normalization"]
    assert "per matching event" in kmc["normalization"]

    def check_native(record):
        order = sum(record["gas_partial_pressure_orders"].values())
        target = f"Pa^-{order} s^-1" if order else "s^-1"
        return convert_coefficient(1, record["unit"], target, {"pressure": order})
    assert [check_native(mkm["rows"][0][d]) for d in ("forward", "reverse")] == pytest.approx([1e-5, 1])
    assert [check_native(e) for e in kmc["events"]] == pytest.approx([1e-5, 1])
    report = read("phase3_0/result.json")
    pair = basis("reference_site_pair", inventory_ids=["top-Ni", "bridge-Cu"])
    pool = basis("reference_site", inventory_ids=["top-Ni", "bridge-Cu"])
    analysis = read("phase3_1/closed_cycle/analysis.json")
    counts = analysis["normalization"]["sites_per_reference"]
    proof = evidence("sites_per_reference", sum(counts.values()), "1", pool, pair)
    proof["source"] = {"path": "reports/multiphase/phase3_1/closed_cycle/analysis.json",
                       "sha256": sha256_file(root / "phase3_1/closed_cycle/analysis.json")}
    result = convert_native_rate(report["overall_rate"], "net_progress", pair, pool, evidence=proof)
    assert result["native_value"] == analysis["tof"]["overall"]["per_site_pair_s"]
    assert result["value"] == analysis["tof"]["overall"]["per_site_s"]


def test_unavailable_reverse_flux_and_independent_net_in_revision_21():
    p = document()
    row = p["reaction_rates"][0]
    row.update(reverse=None, net_evidence=ART)
    validate_rate_output_v2(p)
    del row["net_evidence"]
    with pytest.raises(ValueError, match="independent net_evidence"):
        validate_rate_output_v2(p)
    row.update(reverse="not_applicable", forward=row["net"])
    validate_rate_output_v2(p)


def test_bad_nonfinite_and_scaled_underflow_are_rejected():
    src = basis("surface_area")
    with pytest.raises(ValueError):
        convert_native_rate(float("inf"), "species_source", src, src)
    with pytest.raises(ValueError, match="underflow"):
        convert_native_rate(1e-300, "site_source", dict(src, denominator_value=1e200), src)
    with pytest.raises(ValueError):
        convert_coefficient(float("nan"), "s^-1", "s^-1", {})
