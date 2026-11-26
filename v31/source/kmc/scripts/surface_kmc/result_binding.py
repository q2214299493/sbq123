"""Reconstruct one physical-time window from approved Zacros evidence, entirely offline."""

import argparse
import json
from pathlib import Path

from scripts.replay_evidence import evidence_path
from scripts.artifact_io import sha256_file, sha256_json
from scripts.kinetic_data.scientific_identity import check_binding, dataset_reference, read_artifact
from scripts.kinetic_parameters.engine import check_version
from scripts.multiphase_contracts import read_unique_json as read
from scripts.surface_kmc.analysis import window_analysis
from scripts.surface_kmc.study import replay


def _reader_plan(segment):
    claim = read(evidence_path(segment["run"]) / "claim.json")
    approval = claim["approval"]
    if sha256_json(approval) != segment["approval_sha256"]:
        raise ValueError("Changed segment approval")
    ref = approval.get("reader_bound_plan")
    if not ref:
        raise ValueError("Missing approved reader-bound plan")
    path = evidence_path(ref["path"])
    reader, digest = read_artifact(path)
    if (digest != ref["sha256"] or reader["native_plan_sha256"] != segment["plan_sha256"]
            or sha256_json(reader["native_plan"]) != segment["plan_sha256"]):
        raise ValueError("Changed approved reader-bound or native plan")
    return reader, path.parent


def _approved_sources(lineage, dataset, dataset_hash, config_hash, legacy):
    """Walk verified approvals in writer order; semantic versions alone cannot attest file bytes."""
    writer_sources = None
    network_identity = None
    for segment in lineage:
        reader, directory = _reader_plan(segment)
        folder = evidence_path(reader.get("frozen_artifact_directory", directory))
        references = reader.get("reference_sha256", {})
        for name, supplied in (("dataset", dataset_hash), ("configuration", config_hash)):
            filename = name + ".json"
            expected = reader.get(name + "_sha256", references.get(filename))
            if expected != supplied or references.get(filename, expected) != expected:
                raise ValueError(f"Supplied {name} differs from approved bytes")
            original = folder / filename
            # Legacy continuation plans cite the same frozen bytes provided by their writer.
            if (legacy and writer_sources and "frozen_artifact_directory" not in reader
                    and not original.exists()):
                original = writer_sources / filename
            if not original.is_file() or sha256_file(original) != expected:
                raise ValueError(f"Missing or changed approved original {name}")
        if writer_sources is None:
            writer_sources = folder
        expected = reader.get("network_sha256", references.get("network.json"))
        if legacy and expected is None:
            continue
        if not expected or references.get("network.json", expected) != expected:
            raise ValueError("Missing or conflicting approved original reaction-network digest")
        original = folder / "network.json"
        if not original.is_file():
            raise ValueError("Missing approved original reaction-network source")
        network, raw_hash = read_artifact(original)
        if raw_hash != expected:
            raise ValueError("Original reaction-network bytes differ from approval")
        check_version(network, "network_version")
        if (network["format"] != "reaction-network/1" or network["network_version"] != dataset["network_version"]
                or network["project_id"] != dataset["project_id"]):
            raise ValueError("Approved reaction-network identity differs from dataset")
        identity = dict(file_sha256=raw_hash, network_version=network["network_version"])
        if network_identity is not None and identity != network_identity:
            raise ValueError("Checkpoint segments bind different reaction-network bytes")
        network_identity = identity
    return network_identity


def bind_window(dataset_path, configuration_path, run, start_s, end_s):
    binding, _ = _window(dataset_path, configuration_path, run, start_s, end_s, legacy=False)
    return binding


def verify_window(recorded, dataset_path, configuration_path, run, start_s, end_s):
    """Verify an existing sidecar; historical v1 cannot attest approved network bytes."""
    legacy = recorded.get("format") == "kmc-window-binding/1"
    binding, _ = _window(dataset_path, configuration_path, run, start_s, end_s, legacy=legacy)
    check_binding(recorded, binding)


def verified_window_series(recorded, dataset_path, configuration_path, run):
    """Return the replay used to verify this strict binding, including its event clocks and mapping."""
    if recorded.get("format") != "kmc-window-binding/2":
        raise ValueError("Bridge requires an approved-network v2 window")
    start, end = recorded["definition"]["bounds_s"]
    binding, series = _window(dataset_path, configuration_path, run, start, end, legacy=False)
    check_binding(recorded, binding)
    return series


def _window(dataset_path, configuration_path, run, start_s, end_s, *, legacy):
    dataset, dataset_hash = read_artifact(Path(dataset_path))
    config, config_hash = read_artifact(Path(configuration_path))
    series = replay(dataset, config, run, bind_receipts=True)
    network = _approved_sources(series["receipts"], dataset, dataset_hash, config_hash, legacy)
    observation = window_analysis(series["trajectory"], dataset, series["mapping"], start_s, end_s)
    lineage = series["receipts"]
    leaf = lineage[-1]
    result = dict(plan_sha256=leaf["plan_sha256"], native_receipt_sha256=leaf["receipt_sha256"])
    definition = dict(bounds_s=observation["window_s"], population_rule="left_held",
                      event_interval="(start,end]", basis=observation["basis"], denominator=observation["denominator"])
    parameters = dataset["reactions"][0]["parameter_set"]  # assemble has checked the common conditions.
    conditions = dict(temperature_K=parameters["temperature_K"], pressure_Pa=parameters["pressure_Pa"],
                      partial_pressure_bar=config["partial_pressure_bar"], standard_states=parameters["standard_states"])
    payload = dict(format="kmc-window-binding/1", result=result, checkpoint_lineage=lineage,
                   dataset=dataset_reference(dataset, dataset_hash), configuration_sha256=config_hash,
                   seed=series["seed"], conditions=conditions, definition=definition,
                   site_capacities=series["mapping"]["topology"]["capacities"], observation=observation)
    if not legacy:
        payload.update(format="kmc-window-binding/2", reaction_network=network)
    return dict(payload, window_evidence_sha256=sha256_json(payload)), series


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for label in ("dataset", "configuration", "run"):
        parser.add_argument(label, type=Path)
    parser.add_argument("start", type=float)
    parser.add_argument("end", type=float)
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    inputs = (args.dataset, args.configuration, args.run, args.start, args.end)
    if args.verify:
        binding = read(args.verify)
        verify_window(binding, *inputs)
    else:
        binding = bind_window(*inputs)
    print(json.dumps(binding, indent=2, allow_nan=False))
