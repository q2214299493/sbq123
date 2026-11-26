"""Reconstruct window evidence with a subprocess double and native-format fixtures."""

from copy import deepcopy
import json

import pytest

from scripts.artifact_io import sha256_file, sha256_json
from scripts.kinetic_data.scientific_identity import check_binding
from scripts.surface_kmc.result_binding import bind_window, verify_window
from scripts.surface_kmc.workflow import prepare
from test_kinetic_parameters import case
from test_kmc_workflow import dispatch as workflow_dispatch  # noqa: F401
from test_kmc_workflow import spatial_segment  # noqa: F401


@pytest.fixture
def dispatch(workflow_dispatch, tmp_path):  # noqa: F811
    args, approve, stub, calls = workflow_dispatch

    def reviewed(inputs):
        decision = approve(inputs)
        record = json.loads(decision.read_bytes())
        folder = tmp_path / (inputs["run"].name + "-frozen")
        folder.mkdir()
        native = prepare(**inputs)[0]
        reader = dict(native_plan=native, native_plan_sha256=sha256_json(native))
        network, _ = case(gas=True)
        for name, value in (("dataset", inputs["dataset"]), ("configuration", inputs["config"]), ("network", network)):
            source = folder / (name + ".json")
            source.write_text(json.dumps(value))
            reader[name + "_sha256"] = sha256_file(source)
        path = folder / "reader-bound-plan.json"
        path.write_text(json.dumps(reader))
        record["reader_bound_plan"] = dict(path=str(path), sha256=sha256_file(path))
        decision.write_text(json.dumps(record))
        return decision

    return args, reviewed, stub, calls


def test_equal_windows_and_three_segment_lineage(spatial_segment, tmp_path):  # noqa: F811
    parent = None
    for name, end, frames in [("first", 5, [0, 4]), ("second", 7, None), ("third", 13, [8, 12])]:
        args, receipt = spatial_segment(name, end, frames, parent)
        assert receipt["status"] == "validated_output"
        parent = args["run"]
    d, c = tmp_path / "dataset.json", tmp_path / "configuration.json"
    for target, key in ((d, "dataset"), (c, "config")):
        target.write_text(json.dumps(args[key]))
    def window(a, b):
        return bind_window(d, c, parent, a, b)

    first, second = window(0, 1e-12), window(1e-12, 2e-12)
    assert first["reaction_network"] == dict(file_sha256=sha256_file(tmp_path / "first-frozen/network.json"),
                                            network_version=args["dataset"]["network_version"])
    for field in first["observation"].keys() - {"window_s"}:
        assert first["observation"][field] == second["observation"][field]
    assert first["result"] == second["result"]
    assert first["window_evidence_sha256"] != second["window_evidence_sha256"]
    check_binding(first, window(0, 1e-12))
    verify_window(first, d, c, parent, 0, 1e-12)
    with pytest.raises(ValueError, match="reconstructed"):
        verify_window(dict(first, reaction_network=None), d, c, parent, 0, 1e-12)
    segments = first["checkpoint_lineage"]
    assert [s["terminal_step"] for s in segments] == [5, 7, 13]
    for previous, following in zip(segments, segments[1:]):
        assert previous["receipt_sha256"] == following["parent_receipt_sha256"]
    assert first["result"]["native_receipt_sha256"] == sha256_file(parent / "result.json")
    for field in ("result", "definition", "window_evidence_sha256", "checkpoint_lineage"):
        forged = deepcopy(first)
        forged[field] = None
        with pytest.raises(ValueError, match="reconstructed"):
            check_binding(forged, first)
    with pytest.raises(ValueError, match="exceeds"):
        window(0, 1e9)
    with (tmp_path / "first" / "restart.inf").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="checkpoint|restart"):
        window(0, 1e-12)


@pytest.mark.parametrize("mutation,reason", [
    ("dataset_space", "Supplied dataset"), ("config_newline", "Supplied configuration"),
    ("reserialized_dataset", "Supplied dataset"), ("changed_network", "reaction-network bytes"),
    ("network_newline", "reaction-network bytes"), ("missing_network", "Missing approved original"),
    ("missing_dataset", "Missing or changed approved original dataset"),
    ("missing_config", "Missing or changed approved original configuration"),
    ("reader_plan", "Changed approved reader-bound"),
])
def test_refuse_new_binding_with_changed_source(spatial_segment, tmp_path, mutation, reason):  # noqa: F811
    args, receipt = spatial_segment("first", 5, [0, 4])
    assert receipt["status"] == "validated_output"
    folder = tmp_path / "first-frozen"
    d, c = tmp_path / "supplied-dataset.json", tmp_path / "supplied-config.json"
    d.write_bytes((folder / "dataset.json").read_bytes())
    c.write_bytes((folder / "configuration.json").read_bytes())
    if mutation == "dataset_space":
        d.write_bytes(d.read_bytes() + b" ")
    elif mutation == "config_newline":
        c.write_bytes(c.read_bytes() + b"\n")
    elif mutation == "reserialized_dataset":
        d.write_text(json.dumps(json.loads(d.read_bytes()), sort_keys=True, indent=2))
    elif mutation == "changed_network":
        network = json.loads((folder / "network.json").read_bytes())
        network["project_id"] += "-other"
        (folder / "network.json").write_text(json.dumps(network))
    elif mutation == "network_newline":
        with (folder / "network.json").open("ab") as stream:
            stream.write(b"\n")
    elif mutation.startswith("missing_"):
        (folder / (mutation.removeprefix("missing_").replace("config", "configuration") + ".json")).unlink()
    else:
        with (folder / "reader-bound-plan.json").open("ab") as stream:
            stream.write(b" ")
    with pytest.raises(ValueError, match=reason):
        bind_window(d, c, args["run"], 0, 1e-12)
