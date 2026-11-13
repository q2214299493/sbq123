from __future__ import annotations

from scripts.runtime_resources import require_repository_context, resource_path

import argparse
from pathlib import Path
import subprocess
import sys

from .adsmind_common import load_yaml, write_json
from .candidate_generation import generate_candidates
from .site_detection import detect_surface_sites


ROOT = Path(__file__).resolve().parents[2]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a fully reviewed adsorption candidate batch.")
    parser.add_argument("--surface", type=Path, required=True)
    parser.add_argument("--sites", type=Path)
    parser.add_argument("--adsorbates", required=True, help="Comma-separated adsorbate names.")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--plan", type=Path, help="Evidence-gated candidate plan JSON.")
    parser.add_argument("--prepare-missing", action="store_true", help="CO compatibility mode: prepare missing inputs without bypassing review.")
    parser.add_argument("--backend", choices=("no_relax", "ase_mlff_relax", "vasp_low_cost_relax"), default="no_relax")
    parser.add_argument(
        "--adsorbate-rules",
        type=Path,
        default=resource_path('configs/adsmind_lite/adsorbate_rules.yaml'),
    )
    args = parser.parse_args()
    if not args.prepare_missing:
        missing = [flag for flag in ("sites", "plan", "output") if getattr(args, flag) is None]
        if missing:
            parser.error("the following arguments are required: " + ", ".join("--" + flag for flag in missing))
    return args


def new_output_directory(base: Path, *, numbered: bool) -> Path:
    """Reserve a new directory exclusively; existing results are never reused."""
    serial = 1
    while True:
        target = base if serial == 1 else base.with_name(f"{base.name}_{serial:03d}")
        try:
            target.mkdir(parents=True, exist_ok=False)
            return target
        except FileExistsError:
            if not numbered:
                raise ValueError(f"Output already exists; choose a new --output/--outdir: {target}") from None
            serial += 1


def prepare_missing_inputs(args: argparse.Namespace, names: list[str]) -> None:
    """Prepare artifacts using their owners; a draft is never treated as approval."""
    repository = require_repository_context(ROOT)
    if names != ["CO"] or args.backend != "no_relax":
        raise ValueError("--prepare-missing supports CO with --backend no_relax only")
    args.surface = args.surface.resolve()
    for label, path in (("surface", args.surface), ("sites JSON", args.sites), ("reviewed plan", args.plan)):
        if path is not None and not path.is_file():
            raise ValueError(f"Missing {label} file: {path}")
    if args.plan is None:
        sidecars = [args.surface.parent / name for name in ("plan.json", "prescreen_plan.json")]
        found = [path for path in sidecars if path.exists()]
        if len(found) > 1:
            raise ValueError("Multiple sidecar plans; select --plan explicitly: " + ", ".join(map(str, found)))
        if found:
            if not found[0].is_file():
                raise ValueError(f"Sidecar plan is not a file: {found[0]}")
            args.plan = found[0]
    # The active surface and its family come from repository policy, not skill defaults.
    surface_name = load_yaml(repository / "configs/skill_routing.yaml")["pre_calculation_adsorption_motif_gate"]["allowed_surface_name"]
    surfaces_config = resource_path("configs/adsmind_lite/surfaces.yaml", repository=repository)
    families = load_yaml(surfaces_config)["surface_families"]
    matches = [name for name, rule in families.items() if surface_name in rule.get("examples", [])]
    if len(matches) != 1:
        raise ValueError(f"Cannot identify one configured surface family for {surface_name}")
    default_output = repository / "modules/adsmind_lite/data/candidates/co_candidates"
    args.output = new_output_directory((args.output or default_output).resolve(), numbered=args.output is None)
    inputs = args.output / "_inputs"
    if args.sites is None or args.plan is None:
        inputs.mkdir()
    if args.sites is None:
        args.sites = inputs / "sites.json"
        sites = detect_surface_sites(
            args.surface, surface_name, matches[0], surfaces_config,
            resource_path("configs/adsmind_lite/site_rules.yaml", repository=repository),
        )
        write_json(args.sites, sites)
    if args.plan is None:
        args.plan = inputs / "plan.json"
        result = subprocess.run([
            sys.executable, "-m", "scripts.adsmind_lite.plan_adsorption_candidates",
            "--species", "CO", "--surface-name", surface_name,
            "--adsorbate-rules", str(args.adsorbate_rules.resolve()), "--output", str(args.plan),
        ], cwd=repository, check=False)
        if result.returncode:
            raise ValueError(f"Repository planner failed (exit {result.returncode}); preparation retained at {args.output}")
    print(f"sites={args.sites} plan={args.plan} output={args.output}", flush=True)


def main() -> None:
    args = parse_args()
    names = [value.strip() for value in args.adsorbates.split(",") if value.strip()]
    try:
        if args.prepare_missing:
            prepare_missing_inputs(args, names)
        records = generate_candidates(args.surface, args.sites, names, args.adsorbate_rules, args.output, args.plan, args.backend)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None
    failed = sum(not record.get("initial_structure") for record in records)
    print(f"requested={len(names)} generated={len(records) - failed} failed={failed} backend={args.backend} submitted=0")


if __name__ == "__main__":
    main()
