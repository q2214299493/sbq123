"""Public bridge checks using approved synthetic claims and a mocked Zacros process."""
from copy import deepcopy
import json

import pytest

from scripts.artifact_io import sha256_file, sha256_json
from scripts.rate_output_v2 import validate_network_bound_rate_output
from scripts.surface_kmc.result_binding import bind_window
from scripts.surface_kmc.window_bridge import _observables, bridge
from test_kmc_result_binding import dispatch, workflow_dispatch, spatial_segment  # noqa: F401


def manifest_for(root, run, start, end):
    folder = root / (run.name + "-frozen")
    paths = {key: folder / (key + ".json") for key in ("dataset", "configuration", "network")}
    window = bind_window(paths["dataset"], paths["configuration"], run, start, end)
    paths["window"] = root / f"window-{start}-{end}.json"
    paths["window"].write_text(json.dumps(window))
    manifest = root / f"manifest-{start}-{end}.json"
    refs = {k: dict(path=p.relative_to(root).as_posix(), sha256=sha256_file(p)) for k, p in paths.items()}
    manifest.write_text(json.dumps(dict(format="kmc-window-sources/1", artifacts=refs)))
    return manifest


def test_event_time_oracle_and_equal_windows(spatial_segment, tmp_path):  # noqa: F811
    args, _ = spatial_segment("writer", 5, [0, 4])
    run = args["run"]

    def record(a, b):
        manifest = manifest_for(tmp_path, run, a, b)
        doc = json.loads(manifest.read_bytes())
        mapping = tmp_path / "intact.json"
        mapping.write_text(json.dumps(dict(format="kmc-intact-desorptions/1",
                                           network_sha256=doc["artifacts"]["network"]["sha256"],
                                           intact_desorptions=[dict(reaction_id="ads", direction="reverse",
                                                                    surface_species="H2-bridge", gas_species="H2-g")])))
        doc["artifacts"]["molecular_mapping"] = dict(path=mapping.name, sha256=sha256_file(mapping))
        manifest.write_text(json.dumps(doc))
        return bridge(manifest, sha256_file(manifest))

    result = record(0.25, 3.25)
    rates = result["rate_output"]
    validate_network_bound_rate_output(rates, tmp_path / "writer-frozen/network.json")
    r, = rates["reaction_rates"]
    assert [r[key] for key in ("forward", "reverse", "net")] == pytest.approx([2 / 3, 1 / 3, 1 / 3])
    assert rates["native_normalization"]["denominator_value"] == 1
    values = result["observations"]
    assert values["mean_molecules_per_cell"]["H2-bridge"] == pytest.approx(1.25 / 3)
    assert {r["process"]: r["event_count"] for r in values["directional_exchange"]} == {"adsorption": 2, "desorption": 1}
    for sid, capacity in (("top-Ni", 4), ("bridge-Cu", 3)):
        use = values["time_weighted_site_utilization"][sid]
        assert use["capacity_sites"] == capacity
        assert use["occupied_fraction"] == pytest.approx(1.25 / (3 * capacity))
        assert use["vacancy_fraction"] == pytest.approx(1 - use["occupied_fraction"])
    assert values["residence_exposure_over_desorptions"]["H2-bridge"]["estimate_s"] == pytest.approx(1.25)
    assert result["statistics"]["effective_sample_size"] is None
    first, second = record(0, 0.25), record(0.25, 0.5)
    assert first["observations"] == second["observations"]
    assert first["observations"]["residence_exposure_over_desorptions"]["H2-bridge"]["estimate_s"] is None
    assert first["window"]["result"] == second["window"]["result"]
    assert first["window"]["window_evidence_sha256"] != second["window"]["window_evidence_sha256"]
    assert first["record_sha256"] != second["record_sha256"]
    assert result.pop("record_sha256") == sha256_json(result)


@pytest.mark.parametrize("change", ["manifest", "missing_network", "source_bytes", "window_bytes",
                                     "normalization", "missing_clock", "broken_writer", "wrong_species_network", "unobserved_tail"])
def test_modified_or_incomplete_evidence(spatial_segment, tmp_path, change):  # noqa: F811
    writer, _ = spatial_segment("writer", 5, [0, 4])
    args, _ = spatial_segment("child", 7, None, writer["run"])
    path = manifest_for(tmp_path, args["run"], 0, 3)
    digest = sha256_file(path)
    doc = json.loads(path.read_bytes())
    refs = doc["artifacts"]
    if change == "manifest":
        path.write_bytes(path.read_bytes() + b" ")
    elif change == "missing_network":
        del refs["network"]
    elif change == "source_bytes":
        p = tmp_path / refs["dataset"]["path"]
        p.write_bytes(p.read_bytes() + b" ")
    elif change == "window_bytes":
        p = tmp_path / refs["window"]["path"]
        p.write_bytes(p.read_bytes() + b" ")
    elif change == "normalization":
        p = tmp_path / refs["window"]["path"]
        w = json.loads(p.read_bytes())
        w["definition"]["denominator"] = w["observation"]["denominator"] = 7
        p.write_text(json.dumps(w))
        refs["window"]["sha256"] = sha256_file(p)
    elif change == "wrong_species_network":
        # Real dissociative archive: similar labels and site demand, different molecular products.
        from pathlib import Path
        other = Path(__file__).resolve().parents[1] / "archive/v221_catkinas/nicu-v221-400k-001/network.json"
        refs["network"] = dict(path=str(other), sha256=sha256_file(other))
    elif change == "unobserved_tail":
        # The valid run stops at 7 s, but the last event-one sample is at 6 s.
        with pytest.raises(ValueError, match="exceeds finite sampled evidence"):
            manifest_for(tmp_path, args["run"], 0, 6.5)
        return
    elif change == "missing_clock":
        (writer["run"] / "specnum_output.txt").unlink()
    else:
        with (writer["run"] / "restart.inf").open("ab") as f:
            f.write(b"changed")
    if change in ("missing_network", "normalization", "wrong_species_network"):
        path.write_text(json.dumps(doc))
        digest = sha256_file(path)
    with pytest.raises((ValueError, FileNotFoundError)):
        bridge(path, digest)


@pytest.mark.parametrize("change", ["mapping_bytes", "network", "direction", "product", "duplicate"])
def test_desorption_mapping_bound_to_specific_event(spatial_segment, tmp_path, change):  # noqa: F811
    args, _ = spatial_segment("writer", 5, [0, 4])
    path = manifest_for(tmp_path, args["run"], 0, 4)
    manifest = json.loads(path.read_bytes())
    entry = dict(reaction_id="ads", direction="reverse", surface_species="H2-bridge", gas_species="H2-g")
    mapping = dict(format="kmc-intact-desorptions/1", network_sha256=manifest["artifacts"]["network"]["sha256"],
                   intact_desorptions=[entry])
    if change == "network":
        mapping["network_sha256"] = "a" * 64
    elif change == "direction":
        entry["direction"] = "forward"
    elif change == "product":
        entry["gas_species"] = "another"
    elif change == "duplicate":
        mapping["intact_desorptions"].append(entry)
    evidence = tmp_path / "mapping.json"
    evidence.write_text(json.dumps(mapping))
    manifest["artifacts"]["molecular_mapping"] = dict(path=evidence.name, sha256=sha256_file(evidence))
    if change == "mapping_bytes":
        evidence.write_bytes(evidence.read_bytes() + b" ")
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="(?i)molecular.*mapping"):
        bridge(path, sha256_file(path))


def test_residence_loss_identity(spatial_segment, tmp_path):  # noqa: F811
    args, _ = spatial_segment("writer", 5, [0, 4])
    manifest = manifest_for(tmp_path, args["run"], 0, 4)
    doc = json.loads(manifest.read_bytes())["artifacts"]
    data, network, win = (json.loads((tmp_path / doc[k]["path"]).read_bytes()) for k in ("dataset", "network", "window"))
    _, unmapped = _observables(data, network, win)
    lost = unmapped["residence_exposure_over_desorptions"]["H2-bridge"]
    assert lost["estimate_s"] is None and lost["unavailable_reason"] == "missing_molecular_identity_mapping"
    assert lost["state_exits"] > 0 and lost["molecular_desorptions"] == 0
    assert lost["exposure_per_state_exit_s"] == lost["molecule_seconds"] / lost["state_exits"]
    from scripts.surface_kmc.window_bridge import _exit_kind
    species = {r["species_id"]: deepcopy(r) for r in data["species"]}
    species["H2-bridge"]["configuration_id"] = "trans"
    species["H2-g"]["configuration_id"] = "cis"
    assert _exit_kind(data["reactions"][0]["direction"]["reverse"], species, True) == "configuration_change"
    wrong = deepcopy(network)
    next(s for s in wrong["species"] if s["species_id"] == "H2-bridge")["composition"] = {"H": 1}
    with pytest.raises(ValueError, match="molecular identities"):
        _observables(data, wrong, win)
    # Another allowed loss channel disqualifies exposure/desorptions even if its observed count is zero.
    row = deepcopy(data["reactions"][0])
    row.update(reaction_id="transfer", direction=dict(forward=dict(reactants={"H2-bridge": 1},
                                                                  products={"H2-top": 1}), reverse=None))
    data["reactions"].append(row)
    win["observation"]["pathway_flux"]["transfer"] = dict(forward=0, reverse=0, net_rate=0)
    rates, obs = _observables(data, network, win)
    assert rates["transfer"]["reverse"] == "not_applicable"
    est = obs["residence_exposure_over_desorptions"]["H2-bridge"]
    assert est["estimate_s"] is None and est["unavailable_reason"] == "other_or_unresolved_loss_channel"
