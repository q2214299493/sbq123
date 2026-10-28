"""Bounded source inventory and immutable reads inside explicit task scopes."""
from __future__ import annotations

from datetime import datetime, timezone
from collections import deque
from pathlib import Path
import shutil

from scripts.artifact_io import load_json_object, sha256_file, sha256_json, write_json_exclusive
from scripts.ts_strategy_engine.review_evidence import _no_links


TEXT_NAMES = {"INCAR", "KPOINTS", "POSCAR", "CONTCAR", "OSZICAR", "OUTCAR", "DIMCAR", "MODECAR"}
TEXT_SUFFIXES = {".json", ".jsonl", ".yaml", ".yml", ".md", ".txt", ".out", ".log", ".lsf", ".sh", ".spec",
                 ".py", ".err", ".stderr", ".stdout", ".csv", ".tsv", ".toml"}
DENIED_PARTS = {".git", ".codex", ".ssh", "__pycache__", "node_modules", "scientific-problem-compiler"}
DENIED_NAMES = {"POTCAR", "WAVECAR", "CHGCAR", "CHG", "DOSCAR", "EIGENVAL", "auth.json", "config.toml", ".env"}


def blocked(path: Path) -> bool:
    return bool({p.lower() for p in path.parts} & DENIED_PARTS) or path.name.lower() in {p.lower() for p in DENIED_NAMES} \
        or any(part.lower().startswith(".codex") for part in path.parts) \
        or path.name.lower().startswith(".env") \
        or any(word in path.name.lower() for word in ("credential", "password", "id_ed25519", "token-cache"))


class Catalog:
    def __init__(self, scopes: list[Path], output: Path, *, mode: str = "daily", manifest: Path | None = None):
        if mode not in {"daily", "evaluation"} or not scopes:
            raise ValueError("explicit task scope and daily/evaluation mode required")
        self.output, self.mode = output, mode
        self.scopes = []
        for scope in scopes:
            _no_links(scope.absolute())
            root = scope.resolve(strict=True)
            if blocked(root) or not root.is_dir() or root == Path(root.anchor):
                raise ValueError("invalid research task scope")
            self.scopes.append(root)
        self.allowed = None
        if mode == "evaluation":
            if manifest is None:
                raise ValueError("evaluation requires an explicit frozen file manifest")
            _no_links(manifest.absolute())
            if blocked(manifest.absolute()) or manifest.stat().st_size > 1024 * 1024:
                raise ValueError("invalid or oversized evaluation manifest")
            document = load_json_object(manifest)
            if set(document) != {"schema_version", "files"} or document["schema_version"] != 1:
                raise ValueError("invalid evaluation manifest")
            self.allowed = {}
            for row in document["files"]:
                if set(row) != {"path", "sha256"}:
                    raise ValueError("evaluation files require path/hash")
                path = self.check(Path(row["path"]))
                if path.name.lower() in {"answer.json", "answers.json", "recommendations.json", "reference.json", "expected.json", "model-response.txt", "model-final.txt"}:
                    raise ValueError("reference/answer artifact forbidden in evaluation input")
                if sha256_file(path) != row["sha256"]:
                    raise ValueError("frozen evaluation source changed")
                self.allowed[path] = row["sha256"]
        self.entries = {}
        self.paths = {}
        self.frozen = {}
        self.scan_truncated = False
        for i, root in enumerate(self.scopes):
            self.add(root, i)
            self.discover(root, i, 2)

    def check(self, path: Path) -> Path:
        path = path.absolute()
        if ".." in path.parts or blocked(path) or not any(path.is_relative_to(r) for r in self.scopes):
            raise ValueError("source outside task scope or excluded")
        _no_links(path)
        path = path.resolve(strict=True)
        if not any(path.is_relative_to(r) for r in self.scopes):
            raise ValueError("resolved source escapes scope")
        return path

    def add(self, path: Path, scope: int) -> str | None:
        path = self.check(path)
        if self.allowed is not None and path.is_file() and path not in self.allowed:
            return None
        if self.allowed is not None and path.is_dir() and not any(p.is_relative_to(path) for p in self.allowed):
            return None
        if path.is_file() and path.suffix.lower() not in TEXT_SUFFIXES | {".sqlite3", ".db"} and path.name not in TEXT_NAMES:
            return None
        identity = "S" + sha256_json({"scope": scope, "relative": str(path.relative_to(self.scopes[scope]))})[:16]
        kind = "directory" if path.is_dir() else self.kind(path)
        self.entries[identity] = {"id": identity, "scope": scope, "relative_path": path.relative_to(self.scopes[scope]).as_posix() or ".",
                                  "type": kind, "bytes": path.stat().st_size if path.is_file() else None,
                                  "availability": "withheld", "coverage": "directory metadata only" if path.is_dir() else "file identity; contents not yet supplied"}
        self.paths[identity] = path
        return identity

    @staticmethod
    def kind(path: Path) -> str:
        if path.name in TEXT_NAMES:
            return "calculation_input" if path.name in {"INCAR", "KPOINTS", "POSCAR", "MODECAR"} else "calculation_output"
        if path.suffix in {".sqlite3", ".db"}:
            return "history_database"
        if path.suffix in {".py", ".sh", ".lsf"}:
            return "source_code_not_execution_authority"
        if any(v in path.name.lower() for v in ("review", "outcome", "feedback", "decision", "assessment")) or any(
                part.lower() in {"feedback", "reviews", "attempts", "outcomes"} for part in path.parts[:-1]):
            return "historical_interpretation"
        return "document"

    def discover(self, root: Path, scope: int, depth: int):
        pending = deque([(root, depth)])
        added = 0
        while pending:
            directory, remaining = pending.popleft()
            for path in sorted(directory.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
                if len(self.entries) >= 2000 or added >= 120:
                    self.scan_truncated = True
                    return
                if blocked(path):
                    continue
                if path.is_dir() and path.name.lower() in {"archive", "archives", "backup", "backups", ".cache"}:
                    continue
                try:
                    known = self.listed(path)
                    identity = self.add(path, scope)
                    added += bool(identity and known is None)
                    if identity and path.is_dir() and remaining > 0:
                        pending.append((path, remaining - 1))
                except (OSError, ValueError):
                    continue

    def resolve(self, identity: str, *, directory: bool | None = None) -> Path:
        if identity not in self.paths:
            raise ValueError("unlisted source ID; use evidence.list first")
        path = self.check(self.paths[identity])
        if directory is not None and path.is_dir() != directory:
            raise ValueError("source kind mismatch")
        return path

    def listed(self, path: Path) -> str | None:
        return next((key for key, value in self.paths.items() if value == path), None)

    def snapshot(self) -> dict:
        entries = sorted(self.entries.values(), key=lambda r: (r["relative_path"] != ".", r["scope"], r["relative_path"]))
        return {"mode": self.mode, "scopes": [str(p) for p in self.scopes], "entries": entries[:100],
                "listed_count": len(entries), "initial_display_truncated": len(entries) > 100,
                "scan_truncated": self.scan_truncated, "contents_supplied": False,
                "daily_history": "Historical reviews may be read as interpretations, not primary proof." if self.mode == "daily" else "History queries disabled in evaluation.",
                "evaluation": "Only manifest-bound files are readable; no hidden reference retrieval."}

    def listing(self, ids: list[str], query: str, limit: int) -> dict:
        for identity in ids:
            path = self.resolve(identity, directory=True)
            self.discover(path, self.entries[identity]["scope"], 2)
        roots = [self.resolve(i, directory=True) for i in ids] or self.scopes
        terms = query.lower().split()
        rows = [row for identity, row in self.entries.items() if any(self.paths[identity].is_relative_to(p) for p in roots)
                and (not terms or any(t in row["relative_path"].lower() for t in terms))]
        return {"matches": rows[:limit], "matching_count": len(rows), "truncated": len(rows) > limit, "scope_limited": True}

    def freeze(self, path: Path) -> tuple[Path, dict]:
        path = self.check(path)
        if self.allowed is not None and path not in self.allowed:
            raise ValueError("file withheld by evaluation manifest")
        if path in self.frozen:
            target, reference = self.frozen[path]
            if sha256_file(path) != reference["sha256"]:
                raise ValueError("source changed after its first read")
            return target, reference
        if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("unsupported or oversized source; requires bounded external collection")
        if sum(ref["bytes"] for _, ref in self.frozen.values()) + path.stat().st_size > 256 * 1024 * 1024:
            raise ValueError("run collection byte budget exhausted")
        before = path.stat()
        digest = sha256_file(path)
        if self.allowed is not None and digest != self.allowed[path]:
            raise ValueError("evaluation source changed")
        folder = self.output / "sources" / digest
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / path.name
        if not target.exists():
            shutil.copyfile(path, target)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns) or sha256_file(target) != digest or sha256_file(path) != digest:
            raise ValueError("source changed during collection")
        reference = {"path": str(path), "sha256": digest, "snapshot": str(target), "bytes": before.st_size,
                     "collected_at": datetime.now(timezone.utc).isoformat(), "kind": self.kind(path)}
        self.frozen[path] = target, reference
        return target, reference

    def file(self, directory: Path, name: str) -> tuple[Path | None, dict]:
        path = directory / name
        if not path.is_file():
            return None, {"name": name, "availability": "not_found", "scope": str(directory), "retention_elsewhere": "unknown"}
        if self.allowed is not None and path not in self.allowed:
            return None, {"name": name, "availability": "withheld", "reason": "not in frozen evaluation manifest"}
        frozen, reference = self.freeze(path)
        return frozen, {**reference, "name": name, "availability": "withheld",
                        "provided_to_model": "selected parsed results/excerpts only; complete raw bytes retained by host"}

    def verify(self):
        for path, (snapshot, reference) in self.frozen.items():
            if sha256_file(path) != reference["sha256"] or sha256_file(snapshot) != reference["sha256"]:
                raise ValueError("source/snapshot changed after tool execution")

    def save(self, path: Path):
        write_json_exclusive(path, self.snapshot())
