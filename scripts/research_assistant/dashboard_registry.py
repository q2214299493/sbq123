"""Display-only content-addressed registration and serialized atomic rebuilds."""
from contextlib import contextmanager
import os
from pathlib import Path
import time

from scripts.artifact_io import write_json_atomic, write_json_exclusive
from scripts.ts_strategy_engine.review_evidence import _no_links

from .dashboard_data import build_run
from .dashboard_sources import reference, read_json, Sources, bounded_paths
from .dashboard_render import write_view
from .policies import utc_now
from .catalog import blocked


@contextmanager
def display_lock(folder, timeout=10):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "render.lock"
    _no_links(path, missing_ok=True)
    with path.open("a+b") as handle:
        if os.fstat(handle.fileno()).st_size == 0:
            handle.write(b"0")
            handle.flush()
        until = time.monotonic() + timeout
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= until:
                    raise ValueError("dashboard rebuild busy; registrations retained, rebuild later")
                time.sleep(0.025)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def register(folder, run):
    _no_links(folder.absolute(), missing_ok=True)
    if blocked(folder):
        raise ValueError("excluded dashboard registration directory")
    receipt_ref = reference(Path(run).absolute() / "run_receipt.json")
    read_json(Path(receipt_ref["path"]), receipt_ref)
    registry = folder / "registrations"
    registry.mkdir(parents=True, exist_ok=True)
    path = registry / (receipt_ref["sha256"] + ".json")
    payload = {"schema_version": 1, "run_receipt_ref": receipt_ref}
    try:
        write_json_exclusive(path, payload)
    except FileExistsError:
        if read_json(path) != payload:
            raise ValueError("existing dashboard registration differs; do not overwrite")
    return receipt_ref


def registration_record(path):
    record = read_json(path)
    ref = record.get("run_receipt_ref")
    if record.get("schema_version") != 1 or not isinstance(ref, dict) or set(ref) != {"path", "sha256"} \
            or path.stem != ref["sha256"]:
        raise ValueError("invalid dashboard registration identity")
    return record


def rebuild(folder, output=None, preferred=None):
    folder, output = Path(folder).absolute(), Path(output or folder).absolute()
    _no_links(folder, missing_ok=True)
    _no_links(output, missing_ok=True)
    with display_lock(folder):
        paths = bounded_paths((folder / "registrations").glob("*.json"))
        runs, sources, views = [], Sources(), {}
        for path in paths:
            record = sources.attempt("registration", str(path), lambda: registration_record(path))
            if not record:
                continue
            ref = record["run_receipt_ref"]
            run = Path(ref["path"]).parent
            data = sources.attempt("run_projection", ref, lambda: build_run(run, ref))
            if data is None:
                data = {"schema_version": 1, "kind": "rsi_dashboard_run", "generated_at": utc_now(), "run_receipt_ref": ref,
                        "run": {"path": str(run), "id": ref["sha256"], "name": run.name, "status": "unknown"},
                        "source_errors": [sources.errors[-1]], "usage_state": "unknown", "provided_count": None}
            data.update({"source_root": str(Path(__file__).resolve().parents[2]), "python": os.sys.executable})
            runs.append(data)
            if run not in views or data["run"].get("status") != "unknown":
                views[run] = data
        for run, data in views.items():
            sources.attempt("run_view_write", str(run / "views"), lambda: write_view(run / "views", "rsi_view", data))
        prior_path = output / "index.json"
        prior = sources.attempt("display_preference", str(prior_path), lambda: read_json(prior_path)) if prior_path.exists() else None
        preference = preferred or (prior.get("preferred_run_id") if prior else None)
        document = {"schema_version": 1, "kind": "rsi_dashboard_project", "generated_at": utc_now(), "runs": runs,
                    "preferred_run_id": preference,
                    "source_errors": sources.errors, "registration_root": str(folder / "registrations"),
                    "source_root": str(Path(__file__).resolve().parents[2]), "python": os.sys.executable}
        started = time.perf_counter()
        write_view(output, "index", document)
        elapsed = time.perf_counter() - started
        write_json_atomic(output / "render_receipt.json", {"schema_version": 1, "generated_at": utc_now(),
            "render_seconds": elapsed, "run_receipt_refs": [r["run_receipt_ref"] for r in runs], "source_errors": sources.errors})
    return {"status": "DASHBOARD_GENERATED", "index": str(output / "index.html"), "runs": len(runs),
            "source_errors": len(sources.errors) + sum(len(r.get("source_errors", [])) for r in runs), "render_seconds": elapsed}
