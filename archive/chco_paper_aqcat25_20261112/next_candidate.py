"""Continue BA-Sella from the previous candidate with one newly trained model.

Prediction only: no IDPP, DFT, training, model promotion, or scientific acceptance.
The original initial_candidate.py is imported unchanged as the shared guard owner.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import signal
import sys
from pathlib import Path

FT512 = "cdd391d39ed19fc1ef3516d41b1af53bd81351d8ad73f25e537be232fd8c0dc0"


def require(passed: bool, message: str) -> None:
    if not passed:
        raise ValueError(message)


def write_candidate_output(candidate, output, common):
    path = output / "predicted_candidate.vasp"
    common.write(path, candidate, format="vasp", direct=True, sort=False)
    # ASE closes a path-owned VASP handle before write() returns.
    return {"path": str(path), "sha256": common.digest(path)}


def load_common():
    spec = importlib.util.spec_from_file_location("paper_initial_common", Path(__file__).with_name("initial_candidate.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def bound_json(ref, common):
    require(common.digest(ref["path"]) == ref["sha256"], f"bound source bytes changed: {ref['path']}")
    return json.loads(Path(ref["path"]).read_text(encoding="utf-8"))


def training_bindings(request, common):
    require(common.FT512 == FT512, "shared worker does not identify the frozen FT512 base")
    original = bound_json(request["initial_request"], common)
    result = bound_json(request["training_result"], common)
    training = bound_json(request["training_request"], common)
    require(original["checkpoint"]["sha256"] == result["base_checkpoint_sha256"] == training["base_checkpoint"]["sha256"] == FT512,
            "training did not reset to the frozen FT512 base")
    require(result["document_kind"] == "aqcat25_paper_single_label_training_result" and
            result["status"] == "completed_candidate_only", "training result is not a completed candidate")
    require(result["protocol_sha256"] == training["protocol_sha256"] == request["protocol_sha256"], "training protocol mismatch")
    require(result["training_request_artifact_sha256"] == request["training_request"]["sha256"], "training request artifact mismatch")
    samples = training["training_samples"]
    require(len(samples) == 1 and samples[0]["label"]["structure"]["sha256"] == request["previous_candidate"]["sha256"],
            "trained label is not the previous candidate geometry")
    evidence = result["training_evidence"]
    require(all(evidence.get(key) == 100 for key in ("completed_epochs", "completed_steps", "observed_optimizer_updates"))
            and evidence["optimizer_update_events"] == [{"step": i, "epoch": float(i)} for i in range(1, 101)],
            "100 real epochs/optimizer updates are not recorded")
    checkpoint = request["checkpoint"]
    require(checkpoint["sha256"] != FT512 and checkpoint["sha256"] == result["checkpoint"]["sha256"]
            and Path(checkpoint["path"]).resolve() == Path(result["checkpoint"]["path"]).resolve(), "new checkpoint/result mismatch")
    require(result.get("production_checkpoint_promotion") is False and result.get("scientific_acceptance") is False,
            "training result cannot promote or accept a model/TS")
    return original


def continuation_geometry(previous, frame, initial, original, common):
    import numpy as np

    require(len(frame) == len(previous) == 49 and frame.get_chemical_symbols() == previous.get_chemical_symbols(), "previous atom order mismatch")
    require(common.fixed(frame) == common.fixed(previous) == original["fixed_indices_zero_based"], "previous SD mask mismatch")
    require(np.array_equal(frame.pbc, previous.pbc) and np.allclose(frame.cell.array, previous.cell.array, atol=1e-12, rtol=0)
            and np.allclose(frame.positions, previous.positions, atol=1e-12, rtol=0), "trajectory last frame differs from previous POSCAR")
    mode = np.asarray(frame.info.get("mode_TS"), dtype=float)
    require(mode.shape == (49, 3) and np.isfinite(mode).all() and np.any(mode != 0)
            and np.all(mode[common.fixed(frame)] == 0), "previous mode_TS must be finite, nonzero and zero on fixed atoms")
    bonds = [[int(row[0]), int(row[1]), str(row[2])] for row in frame.info.get("bonds_TS", [])]
    require(bonds == original["reaction"]["bonds"], "previous trajectory reaction bonds changed")
    common.geometry(frame, initial, original)
    guess = frame.copy()
    common.pilot.validate_reaction_metadata(guess, bonds, original["reaction"]["adsorbate_indices"])
    common.pilot.add_model_context(guess, bonds, original["reaction"]["adsorbate_indices"], False, False)
    guess.info["mode_TS"] = mode.copy()
    return guess


def execute(request, output, report, common):
    import numpy as np

    require(request.get("document_kind") == "paper_sequential_candidate_continuation_request", "wrong continuation request kind")
    artifact = sys.modules.get("artifact_io") or sys.modules.get("scripts.artifact_io")
    required = [__file__, common.__file__, common.pilot.__file__, common.benchmark.__file__, artifact.__file__, common.calculations.__file__]
    sources = {Path(ref["path"]).resolve(): ref for ref in request["source_files"]}
    require(len(sources) == len(request["source_files"]) and all(Path(path).resolve() in sources for path in required), "loaded implementation omitted/duplicated in source manifest")
    original = training_bindings(request, common)
    refs = [*sources.values(), *(request[key] for key in ("checkpoint", "previous_candidate", "previous_trajectory")), original["initial"]]
    for ref in refs:
        require(common.digest(ref["path"]) == ref["sha256"], f"source/input hash mismatch: {ref['path']}")
    tree = common.ast.parse(common.textwrap.dedent(common.inspect.getsource(common.calculations.run_sella_calculation)))
    require(any(isinstance(node, common.ast.Dict) and any(
        isinstance(key, common.ast.Constant) and key.value == "nsteps_per_diag" and
        isinstance(value, common.ast.Constant) and value.value == 1
        for key, value in zip(node.keys, node.values)) for node in common.ast.walk(tree)), "author nsteps_per_diag=1 not verified")
    initial = common.read(original["initial"]["path"], format="vasp")
    previous = common.read(request["previous_candidate"]["path"], format="vasp")
    frame = common.read(request["previous_trajectory"]["path"], index=-1, format="traj")
    guess = continuation_geometry(previous, frame, initial, original, common)
    require(common.torch.cuda.is_available() and common.torch.cuda.device_count() == 1, "exactly one CUDA device required; CPU fallback forbidden")
    inner = common.benchmark._load_calculator("aqcat25", Path(request["checkpoint"]["path"]), "cuda")
    require(inner.trainer.cpu is False, "calculator selected CPU fallback")
    devices = {str(parameter.device) for parameter in inner.trainer.model.parameters()}
    require(devices and all(device.startswith("cuda:") for device in devices), "model parameters are not entirely on CUDA")
    calculator = common.GuardedCalculator(inner, initial, original)
    report.update(model_devices=sorted(devices), source_files=request["source_files"], protocol_sha256=request["protocol_sha256"],
                  cuda={"available": True, "device_count": 1, "build": common.torch.version.cuda},
                  fixed_indices_zero_based=original["fixed_indices_zero_based"],
                  input_bindings={key: request[key] for key in ("initial_request", "training_request", "training_result", "checkpoint", "previous_candidate", "previous_trajectory")},
                  geometry_initialization="previous_trajectory_last_frame", IDPP_performed=False, previous_mode_retained=True)
    report["ba_sella"] = {"fmax": 0.01, "min_steps": 10, "max_steps": 1000, "eta": 0.01, "gamma": 0.05,
                         "delta0": 0.05, "dot_prod_thr": 0.5, "nsteps_per_diag": 1}
    candidate = common.pilot.run_ba_sella(guess, calculator, output, 0.01, 1000, 10)
    report.update(optimizer_status=candidate.info.get("status"), calculator_failure=calculator.failure,
                  candidate_geometry=common.geometry(candidate, initial, original))
    forces = candidate.get_forces()
    report["predicted_movable_fmax_eV_per_A"] = float(np.linalg.norm(forces, axis=1).max())
    report["output_candidate"] = write_candidate_output(candidate, output, common)
    report["optimizer_converged"] = candidate.info.get("status") == "finished" and report["predicted_movable_fmax_eV_per_A"] <= 0.01
    require(not calculator.failure and report["optimizer_converged"], calculator.failure or "BA-Sella unfinished or budget exhausted")
    for ref in refs + [request[key] for key in ("initial_request", "training_request", "training_result")]:
        require(common.digest(ref["path"]) == ref["sha256"], "bound source changed during prediction")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    common = load_common()
    require(common.digest(args.request) == args.request_sha256, "request bytes changed")
    request = json.loads(args.request.read_text(encoding="utf-8"))
    boundary = Path("/home/sbq/sbq")
    require(args.output.is_absolute() and args.output.is_relative_to(boundary)
            and args.output.resolve().is_relative_to(boundary.resolve(strict=True)), "output escapes the declared/canonical GPU boundary")
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"result_class": "predicted_candidate_only", "scientifically_accepted": False, "DFT_performed": False,
              "training_performed": False, "status": "failed", "request_sha256": args.request_sha256}

    def interrupted(signum, _frame):
        raise TimeoutError(f"interrupted by signal {signum}; no automatic retry")

    previous_handler = signal.signal(signal.SIGTERM, interrupted)
    try:
        execute(request, args.output, report, common)
        report["status"] = "prediction_completed_pending_review"
    except Exception as error:
        report["failure"] = f"{type(error).__name__}: {error}"
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
    with (args.output / "candidate_report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
    return 0 if report["status"] == "prediction_completed_pending_review" else 1


if __name__ == "__main__":
    raise SystemExit(main())
