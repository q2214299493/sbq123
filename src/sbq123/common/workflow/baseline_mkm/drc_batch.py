"""Plan a bounded batch against one immutable network, reusing verified native DRC evidence."""

import argparse
from pathlib import Path

from scripts.artifact_io import load_json_object as read, sha256_file
from scripts.baseline_mkm import drc_pair as pair
from scripts.baseline_mkm.drc_report import compare as compare
from scripts.baseline_mkm.drc_batch_plan import (
    LIMITS as LIMITS, eligibility as eligibility, prepare, reuse as reuse, scan,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    inspect = sub.add_parser("scan", help="Inspect reaction eligibility without a native baseline or run preparation")
    for field in ("network", "dataset", "output"):
        inspect.add_argument(field, type=Path)
    for name in ("prepare", "execute", "report"):
        cmd = sub.add_parser(name)
        cmd.add_argument("root", type=Path)
        cmd.add_argument("baseline", type=Path)
        cmd.add_argument({"prepare": "sources", "execute": "approvals", "report": "output"}[name], type=Path)
    args = parser.parse_args()
    if args.action == "scan":
        network = read(args.network)
        result = dict(network_version=network["network_version"], network_sha256=sha256_file(args.network),
                      dataset_sha256=sha256_file(args.dataset), reactions=scan(network, read(args.dataset)), planned_runs=0)
        pair.put(args.output, result)
        return
    root, base = args.root.resolve(), args.baseline.resolve()
    if args.action == "prepare":
        prepare(root, base, read(args.sources))
    elif args.action == "execute":
        from scripts.baseline_mkm.drc_batch_execution import execute

        execute(root, base, read(args.approvals))
    else:
        from scripts.baseline_mkm.drc_batch_report import publish

        publish(root, base, args.output)


if __name__ == "__main__":
    main()
