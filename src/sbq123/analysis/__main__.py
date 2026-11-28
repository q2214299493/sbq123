"""Read-only scientific analysis and follow-up planning from installed SBQ123 result owners."""
import argparse
import json
from pathlib import Path

from sbq123.common.compat import historical_module
from sbq123.common.kinetic_model.contracts import identity
from sbq123.common.evidence.trust import REACTOR_CONTROL_RESULTS


def immutable_json(path):
    def unique(pairs):
        doc = dict(pairs)
        if len(doc) != len(pairs):
            raise ValueError("Duplicate key in scientific report")
        return doc
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def file_qualification(*digests):
    if all(d in REACTOR_CONTROL_RESULTS for d in digests):
        return "archived_numerical_control"
    return "reported_only: independent producer identity has not been established by this CLI"


def arguments(argv):
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="action", required=True)
    for name in ("rates", "study", "point", "window", "retained-window", "reactor", "comparison", "follow-up", "contrast"):
        p = sub.add_parser(name)
        if name == "rates":
            p.add_argument("role", choices=["mkm", "kmc"])
        if name in ("study", "follow-up", "comparison"):
            p.add_argument("root", type=Path, help="Authenticated offline MKM fixture root")
        if name != "study":
            p.add_argument("path", type=Path)
            p.add_argument("sha256", help="Digest from independent producer or release evidence")
        if name == "comparison":
            p.add_argument("--reactor", type=Path, help="Optional independently retained Reactor result")
            p.add_argument("--reactor-sha256")
        if name == "point":
            p.add_argument("--options", type=Path)
        if name == "follow-up":
            p.add_argument("directory", type=Path, help="Local write-once planning output")
        if name == "contrast":
            p.add_argument("right", type=Path)
            p.add_argument("right_sha256")
            p.add_argument("variable", choices=("temperature_K", "pressure_Pa"))
    return cli.parse_args(argv)


def main(argv=None):
    args = arguments(argv)
    if args.action in ("rates", "follow-up"):
        from sbq123.discovery.ranking.scientific_priority.exchange import follow_up_study, investigate
        if args.action == "rates":
            out = investigate(args.role, args.path, expected_sha256=args.sha256)
        else:
            out = follow_up_study(args.root, args.path, args.sha256, args.directory)
    elif args.action == "study":
        from sbq123.analysis.interpretation.kinetics import interpret_sensitivity
        historical_module("mkm", "scripts.scientific_priority.benchmark")
        out = interpret_sensitivity(args.root)
    elif args.action == "point":
        from sbq123.analysis.interpretation.kinetics import interpret_point
        owner = historical_module("mkm", "scripts.baseline_mkm.analysis")
        from scripts.baseline_mkm.result_binding import bind_result
        run = args.path
        binding = bind_result(run)
        if binding["binding_sha256"] != args.sha256:
            raise ValueError("Different MKM point binding")
        receipt = owner.status(run)
        receipt["raw_plan_sha256"] = owner.sha256_json(owner.read(run / "plan.json"))
        report = owner.analyze(run / "network.json", run / "dataset.json", run / "configuration.json",
                               run / "result.json", receipt, args.options)
        out = dict(analysis=report, interpretation=interpret_point(report, identity(report)), binding_sha256=args.sha256)
    elif args.action == "retained-window":
        from sbq123.analysis.interpretation.kinetics import interpret_window
        owner = historical_module("kmc", "scripts.runtime_resources")
        from scripts.multiphase_contracts import read_artifact
        record, digest = read_artifact(owner.resource_path(args.path.as_posix()), expected_sha256=args.sha256)
        out = interpret_window(record, record["record_sha256"])
        out.update(replay="release-retained report", source_file_sha256=digest,
                   limitation="Archived observations retain their original scope; fresh native replay is a separate check.")
    elif args.action == "window":
        from sbq123.analysis.interpretation.kinetics import interpret_window
        bridge = historical_module("kmc", "scripts.surface_kmc.window_bridge").bridge
        window = bridge(args.path, args.sha256, allow_partial_mapping=True)
        out = interpret_window(window, window["record_sha256"])
    elif args.action == "comparison":
        compare = historical_module("kmc", "scripts.kinetic_data.result_comparison").compare
        result = compare(args.path, args.sha256, mkm_worktree=args.root)
        from scripts.scientific_interpretation import summarize_comparison
        out = dict(comparison=result, interpretation=summarize_comparison(result))
        if args.reactor is not None or args.reactor_sha256 is not None:
            from sbq123.analysis.observations.reactor_profiles import analyze_profile, compare_local_mkm
            try:
                if not args.reactor or not args.reactor_sha256:
                    raise ValueError("Reactor result and independent producer digest required")
                reactor = immutable_json(args.reactor)
                out["reactor"] = analyze_profile(reactor, args.reactor_sha256)
                out["reactor_local_mkm"] = compare_local_mkm(reactor, args.reactor_sha256)
                out["reactor_file_qualification"] = file_qualification(args.reactor_sha256)
            except (ValueError, OSError, KeyError) as exc:
                out["reactor"] = dict(status="insufficient_evidence", reason=str(exc))
            out["outlet_minus_native_turnover"] = dict(value=None, reason="An integrated outlet conversion or yield "
                                                       "and a native point or window TOF have different physical definitions.")
    else:
        from sbq123.analysis.observations.reactor_profiles import analyze_profile, compare_local_mkm, compare_operating_points
        result = immutable_json(args.path)
        if args.action == "contrast":
            out = compare_operating_points((result, args.sha256), (immutable_json(args.right), args.right_sha256),
                                           args.variable)
            out["file_qualification"] = file_qualification(args.sha256, args.right_sha256)
            if out["change"] is not None and not {args.sha256, args.right_sha256} <= REACTOR_CONTROL_RESULTS:
                out.update(reported_contrast=out["change"], change=None, status="reported_only")
        else:
            out = dict(profile=analyze_profile(result, args.sha256), local_mkm=compare_local_mkm(result, args.sha256),
                       file_qualification=file_qualification(args.sha256))
    print(json.dumps(out, ensure_ascii=True, allow_nan=False, sort_keys=True))


if __name__ == "__main__":
    main()
