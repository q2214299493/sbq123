"""Preserve task evidence and copy only task-owned changes to the release checkout."""
from pathlib import Path
import shutil
import subprocess
import zipfile

import yaml

from scripts.artifact_io import load_json_object, sha256_file, write_json_exclusive
from .complete_dft import FINAL
from .prepare import EXCEPTION, OUTPUT, ROOT

PUBLISH = Path("C:/Users/86177/.codex/worktrees/fe110-11-15-ft512-dft/work")
DOCS = ROOT / "docs/reviews/fe110_c2_11_15_ft512_20261029"


def document():
    summary = load_json_object(FINAL / "submission_summary.json")
    review = load_json_object(OUTPUT / "ML_results_review.json")
    registered = load_json_object(FINAL / "registration_verification.json")
    if summary["new_VASP_submitted"] != 15 or registered["scientific_result_rows"] != 0:
        raise ValueError("actual15 submissions and metadata-only verification required")
    lines = ["# Fe(110) 11–15: FT512 GPU and DFT submission, 2026-10-29", "",
        "15/15 reviewed v5 seeds completed native AQCat25 CUDA pre-relaxation on MZ73 GPU1.",
        f"Producer span: {review['GPU_elapsed_seconds']:.6f} seconds. Model SHA256:",
        f"`{review['model_checkpoint_sha256']}`. This is the newest development-selected",
        "partial FT512 snapshot, not a promoted or per-species calibrated production model.", "",
        "Every target molecular graph and fixed Fe layer is retained. All15 reached",
        "ML fmax≤0.10 eV/Å;all15 pass work-side endpoint review. Symmetry/permutation-aware",
        "comparison found no duplicates at adsorbate RMSD0.20Å and movable Fe RMSD0.05Å.",
        "All trajectories/raw ML forces, seeds and failures remain preserved. No predicted",
        "energy is admitted as a DFT result, adsorption energy or motif-ranking authority.", "",
        "All15 exact inputs pass the canonical adsorption preflight, read-only INCAR",
        "custodian and independent POSCAR/INCAR/order/mask/graph readback. DFT: PBE/PAW-PBE,",
        "Fe45 five layers/bottom18 fixed, ENCUT400eV, Gamma5×5×1, ISPIN2, Fe2.2μB initial,",
        "ISMEAR1/SIGMA0.20, EDIFF1e-5, EDIFFG−0.02eV/Å, LORBIT11, 32ranks/job, NSW80.",
        "80steps is an agent-selected screening bound;it does not guarantee convergence.", "",
        "Fe/O/C/H POTCAR is the exact [Fe,O,C,H] permutation of the reviewed [Fe,C,O,H]",
        "datasets;licensed contents stay on the VASP server. Its hash is",
        "`cfdeb95d5ce5ab92e2ff0c0cdd1cd3870fbbe3a929822c631e09fd828c511a4f`.",
        "13_A first encountered a pre-reservation rejection because its POTCAR source",
        "used an expanded absolute path. Readback confirmed six SUBMITTED and nine",
        "NOT_RESERVED. A new immutable nine-job bundle/gates binds the same verified",
        "POTCAR bytes through ~/sbq. The six submitted jobs were not repeated;no",
        "existing calculation or gate was overwritten. Both submission stages are retained.", "",
        f"Queue observation: `{summary['checked_at']}`. Queue status alone establishes",
        "neither electronic/ionic convergence nor scientific validity.", "",
        "| Seed | Real LSF job ID | Queue status |", "|---|---:|---|"]
    lines += [f"| {r['name']} | {r['job_id']} | {r['scheduler_status']} |" for r in summary["records"]]
    lines += ["", f"Registry: {registered['registry_rows_read_back']} metadata rows read back;zero scientific result rows.",
        "Primary validation: 35 existing GPU-controller regression tests, then47 scoped",
        "GPU/DFT/input/submission tests passed;Python syntax and scoped Ruff passed.",
        "The isolated source-release checkout passed194 scoped tests. Chemistry/symmetry",
        "helpers and their tests are carried from the published seed-preparation commit3111b274.",
        "repo-state sync --safe-only failed on the existing PKG-INFO classification mismatch;",
        "managed state synchronization did not complete;the classification was not repaired.",
        "DFT completion/SCF/local magnetism/final force/final chemistry and site minima",
        "remain unverified. No speedup ratio or global-minimum claim is made.", "",
        "Next: check these15 jobs on demand, then validate their converged structures",
        "and compare compatible DFT results. No automatic continuation or retry is active.", "",
        "Canonical live evidence: calculations/fe110_c2_adsorption_11_15_20261020/ft512_gpu_20261029_v1/.",
        "The source-release evidence.zip preserves frozen runtime, exact input bytes,",
        "all ML trajectories, canonical gates, actual submission receipts, queue proof",
        "and metadata-only registry transaction. It contains no checkpoint weights or POTCAR.",
        "The GPU stage used an exact backend-policy direct-execution exception and",
        "native request/producer receipts. No scheduler ID or schema-v2 scheduler-based",
        "handoff was fabricated for this direct run. Producer exit0 proves process exit only.", ""]
    (DOCS / "README.md").write_text("\n".join(lines), encoding="utf-8", newline="\n")
    state = ("Fe110 11–15 FT512→DFT2026-10-29:15/15 reviewed v5 seeds GPU-pre-relaxed "
        f"in{review['GPU_elapsed_seconds']:.3f}s;MLfmax≤0.10/graphs/fixedmask/contacts PASS,no duplicates."
        "All15 canonical DFT submissions confirmed:"
        + ",".join(r["name"] + "=" + r["job_id"] + "/" + r["scheduler_status"] for r in summary["records"])
        + ";32ranks/NSW80/EDIFFG−0.02/LORBIT11.13_A absolute POTCAR path rejection occurred before reservation;"
        "nine untouched inputs received new exact gates,firstsix not repeated."
        f"{registered['registry_rows_read_back']} registry metadata readbacks/0scientific results."
        "PartialFT512 experimental,not promoted;DFT convergence/magnetism/final minima and measured speedup unverified."
        "No automatic continuation/retry.Next:on-demand checkpoint and completed-DFT scientific review."
        "Evidence:docs/reviews/fe110_c2_11_15_ft512_20261029/README.md.")
    index = "\n## Fe11011–15 FT512 GPU and DFT (2026-10-29)\n\n- `docs/reviews/fe110_c2_11_15_ft512_20261029/`:scope,15actualjobIDs,input/evidence ZIP and verification.\n- `archive/fe110_11_15_gpu_20261029/`:bounded GPU adapter/transport,frame review,canonical DFT handoff and metadata-only registration.\n- `calculations/fe110_c2_adsorption_11_15_20261020/ft512_gpu_20261029_v1/`:frozen request/runtime,returned15trajectories,DFT inputs/gates/receipts and registry batch.\n"
    backlog = "\n## Fe11011–15 submitted DFT follow-up (2026-10-29)\n\n- GPU and all15DFT submissions are complete;review converged DFT geometry/SCF/local moments/final force and compatible energies on demand. Do not automatically continue or retry. Evidence:docs/reviews/fe110_c2_11_15_ft512_20261029/README.md.\n"
    for base in [ROOT, PUBLISH]:
        for relative, block in [("docs/02_CURRENT_STATE.md", "\n" + state + "\n"), ("docs/05_FILE_INDEX.md", index), ("tasks/backlog.md", backlog)]:
            target = base / relative
            raw = target.read_bytes()
            if "Fe11011–15 FT512 GPU and DFT" in raw.decode("utf-8") or state in raw.decode("utf-8") or (relative == "tasks/backlog.md" and "Fe11011–15 submitted DFT follow-up" in raw.decode("utf-8")):
                raise ValueError("preserve already-written task state:" + str(target))
            target.write_bytes(raw + block.encode("utf-8"))


def copy_sources():
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=PUBLISH)
    if status:
        raise ValueError("publication checkout must be clean before task copy")
    for relative in ["archive/fe110_11_15_gpu_20261029", "docs/reviews/fe110_c2_11_15_ft512_20261029"]:
        source = ROOT / relative
        shutil.copytree(source, PUBLISH / relative, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for relative in ["archive/fe110_pair2_20261027/runtime.py", "tests/test_fe110_11_15_gpu_scope.py", "tests/test_fe110_11_15_dft.py",
            "scripts/adsorption/build_fe110_care_batch.py", "scripts/adsorption/build_fe110_care_isomers.py",
            "tests/test_fe110_care_batch.py", "tests/test_fe110_care_requested_seeds.py"]:
        shutil.copyfile(ROOT / relative, PUBLISH / relative)
    # Restore the already-published exact seed bytes;none exist on this release base.
    prefix = "calculations/fe110_c2_adsorption_11_15_20261020/candidates_v5"
    paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", "-z", "3111b274", "--", prefix], cwd=ROOT).decode().split("\0")
    for relative in filter(None, paths):
        target = PUBLISH / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(subprocess.check_output(["git", "show", "3111b274:" + relative], cwd=ROOT))
    policy_path = PUBLISH / "configs/execution_backends.yaml"
    raw = policy_path.read_bytes().decode("utf-8")
    exception = yaml.safe_load((ROOT / "configs/execution_backends.yaml").read_text(encoding="utf-8"))["backends"]["aqcat_gpu"]["direct_execution_exceptions"][EXCEPTION]
    snippet = yaml.safe_dump({EXCEPTION: exception}, sort_keys=False, allow_unicode=True)
    marker = "    direct_execution_exceptions:\n"
    if raw.count(marker) != 1 or EXCEPTION in raw:
        raise ValueError("ambiguous task-only backend insertion")
    policy_path.write_bytes(raw.replace(marker, marker + "".join("      " + line + "\n" for line in snippet.splitlines()), 1).encode("utf-8"))
    path = PUBLISH / "scripts/adsorption/preflight_fe110_adsorption.py"
    raw = path.read_text(encoding="utf-8")
    marker = '        (("Fe", "C", "H"), (45, 1, 2)),\n'
    added = ''.join('        ' + row + ',\n' for row in ['(("Fe", "C", "H"), (45, 2, 3))', '(("Fe", "C", "H"), (45, 2, 4))', '(("Fe", "C", "O", "H"), (45, 2, 1, 3))', '(("Fe", "O", "C", "H"), (45, 1, 2, 3))'])
    if raw.count(marker) != 1:
        raise ValueError("unexpected release preflight")
    path.write_text(raw.replace(marker, marker + added, 1), encoding="utf-8", newline="\n")
    path = PUBLISH / "tests/test_fe110_adsorption_preflight.py"
    raw = path.read_text(encoding="utf-8")
    source = (ROOT / "tests/test_fe110_adsorption_preflight.py").read_text(encoding="utf-8")
    test = source[source.index('@pytest.mark.parametrize("symbols,counts"'):]
    for row in ['    ("Fe C H", "45 2 1"),\n', '    ("Fe C H", "45 2 2"),\n', '    ("Fe C O H", "45 2 1 1"),\n', '    ("Fe O C H", "45 1 2 1"),\n']:
        test = test.replace(row, "")
    test = test.replace('    ("Fe C H", "45 2 4"),', '    ("Fe C H", "45 2 3"),\n    ("Fe C H", "45 2 4"),')
    path.write_text(raw + "\n\n" + test, encoding="utf-8", newline="\n")
    attributes = PUBLISH / ".gitattributes"
    with attributes.open("ab") as stream:
        stream.write(b"\ncalculations/fe110_c2_adsorption_11_15_20261020/** -text -eol\ncalculations/fe110_c2_adsorption_11_15_20261020/candidates_v5/POSCAR.clean_reference whitespace=-blank-at-eol,-blank-at-eof\ncalculations/fe110_c2_adsorption_11_15_20261020/candidates_v5/geometry_summary.csv whitespace=-blank-at-eol,-blank-at-eof\n")


def package():
    target = DOCS / "evidence.zip"
    files = [p for p in sorted(OUTPUT.rglob("*")) if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
    if any(p.name == "POTCAR" or p.suffix in {".pt", ".pth"} or p.stat().st_size > 5_000_000 for p in files):
        raise ValueError("licensed,model or unbounded runtime file in archive")
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in files:
            bundle.write(path, path.relative_to(OUTPUT).as_posix())
    write_json_exclusive(DOCS / "evidence_manifest.json", {"zip_sha256": sha256_file(target), "file_count": len(files),
        "uncompressed_bytes": sum(p.stat().st_size for p in files), "source_directory": str(OUTPUT),
        "files": [{"path": p.relative_to(OUTPUT).as_posix(), "sha256": sha256_file(p), "bytes": p.stat().st_size} for p in files]})
    shutil.copyfile(target, PUBLISH / target.relative_to(ROOT))
    shutil.copyfile(DOCS / "evidence_manifest.json", PUBLISH / DOCS.relative_to(ROOT) / "evidence_manifest.json")
    shutil.copyfile(DOCS / "README.md", PUBLISH / DOCS.relative_to(ROOT) / "README.md")
    print({"files_preserved": len(files), "ZIP_bytes": target.stat().st_size, "SHA256": sha256_file(target), "publication": str(PUBLISH)}, flush=True)


if __name__ == "__main__":
    copy_sources()
    document()
    package()
