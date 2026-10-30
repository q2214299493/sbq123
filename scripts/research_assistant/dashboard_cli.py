"""Local dashboard entry; generation never starts a model or scientific workflow."""
import os
from pathlib import Path
import sys
import webbrowser

from .catalog import blocked
from .dashboard_sources import read_json, bounded_paths
from .dashboard_registry import register, rebuild
from scripts.ts_strategy_engine.review_evidence import _no_links


def add_command(sub):
    command = sub.add_parser("dashboard", help="Rebuild/open local derived RSI pages; no model calls.")
    scope = command.add_mutually_exclusive_group(required=True)
    scope.add_argument("--run", type=Path)
    scope.add_argument("--runs-root", type=Path, help="Bounded import: immediate run directories only.")
    command.add_argument("--output-dir", type=Path, help="Derived project index directory; run pages remain under run/views.")
    command.add_argument("--open", action="store_true", dest="open_page")


def folder_for(run):
    receipt = read_json(Path(run).absolute() / "run_receipt.json")
    root = receipt.get("rsi_config", {}).get("store")
    return Path(root).absolute() / "dashboard" if root else Path(run).absolute().parent / "rsi_dashboard"


def refresh_run(run, output=None):
    folder = folder_for(run)
    ref = register(folder, run)
    return rebuild(folder, output, preferred=ref["sha256"])


def refresh_store(store):
    folder = Path(store).absolute() / "dashboard"
    if not (folder / "registrations").exists():
        return {"status": "NO_REGISTERED_DASHBOARD_RUNS", "index": None}
    return rebuild(folder)


def automatic(run=None, store=None, disabled=False):
    if disabled:
        return
    try:
        value = refresh_run(run) if run is not None else refresh_store(store)
        print("RSI dashboard: " + str(value.get("index") or value["status"]), file=sys.stderr)
    except Exception as exc:
        print(f"RSI dashboard display failed ({type(exc).__name__}): {exc}; research receipt unchanged, no model retry.", file=sys.stderr)


def execute(args):
    if args.run:
        result = refresh_run(args.run, args.output_dir)
        result["run_view"] = str(args.run.absolute() / "views" / "rsi_view.html")
        target = result["run_view"]
    else:
        root = args.runs_root.absolute()
        _no_links(root)
        if blocked(root) or root == Path(root.anchor):
            raise ValueError("explicit bounded run root required")
        children = bounded_paths(root.iterdir())
        runs = [p for p in children if p.is_dir() and (p / "run_receipt.json").is_file()]
        if (root / "run_receipt.json").is_file():
            runs.insert(0, root)
        folders = {folder_for(run) for run in runs}
        if len(folders) != 1:
            raise ValueError("run root must contain one project/store; choose explicit separate roots")
        folder = folders.pop()
        for run in runs:
            register(folder, run)
        result = rebuild(folder, args.output_dir)
        target = result["index"]
    if args.open_page:
        if os.name == "nt":
            os.startfile(target)
        else:
            webbrowser.open(Path(target).as_uri())
    return result
