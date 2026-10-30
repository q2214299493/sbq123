"""Self-contained, offline HTML. Untrusted source text is data, never markup."""
import json
import os
from pathlib import Path
import tempfile

from scripts.artifact_io import write_json_atomic
from scripts.runtime_resources import resource_path
from scripts.ts_strategy_engine.review_evidence import _no_links


MARKER = "<!-- rsi-dashboard:1 -->"


def render(document):
    assets = resource_path("scripts/research_assistant/dashboard_assets/index.html").parent
    encoded = json.dumps(document, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    encoded = encoded.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    template = (assets / "index.html").read_text(encoding="utf-8")
    static = template.replace("__CSS__", (assets / "view.css").read_text(encoding="utf-8")).replace(
        "__JS__", (assets / "view.js").read_text(encoding="utf-8"))
    return static.replace("__DATA__", encoded, 1)


def write_html(path, text):
    _no_links(path.absolute(), missing_ok=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not path.read_text(encoding="utf-8").startswith(MARKER):
        raise ValueError("refusing to replace a file not owned by RSI dashboard")
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".rsi-view-", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def write_view(folder, name, document):
    _no_links(folder.absolute(), missing_ok=True)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / (name + ".json")
    _no_links(target.absolute(), missing_ok=True)
    if target.exists():
        prior = json.loads(target.read_text(encoding="utf-8"))
        if prior.get("kind") not in {"rsi_dashboard_project", "rsi_dashboard_run"}:
            raise ValueError("refusing to replace an unrelated JSON file")
    write_json_atomic(target, document)
    write_html(folder / (name + ".html"), render(document))
