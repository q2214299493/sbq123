"""Record prepared-only repository state; grants no training/scientific authority."""
import json
import subprocess
import sys
from datetime import datetime, timezone

from scripts.artifact_io import sha256_file, write_json_exclusive

from .prepare import OUTPUT, ROOT


def main():
    files = sorted(str(path.relative_to(ROOT)).replace("\\", "/") for path in (ROOT / "archive/fe110_adsorption_training_comparison_20261019").glob("*.py"))
    source = "scripts/adsorption/force_training_preflight.py"
    commands = [[sys.executable, "-m", "py_compile", source, *files],
                [sys.executable, "-m", "ruff", "check", source, *files],
                ["C:/Program Files/Git/bin/bash.exe", "-n", "scripts/adsorption/role_training_job.sh"]]
    results = []
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False, timeout=60)
        results.append({"command": command, "exit_code": result.returncode,
                        "stdout": result.stdout[:4000], "stderr": result.stderr[:4000]})
    write_json_exclusive(OUTPUT / "validation_commands.json", {"results": results})
    if any(row["exit_code"] for row in results):
        raise RuntimeError("validation failed;preserve record,do not repeat unchanged")
    now = datetime.now(timezone.utc).isoformat()
    prior = "task-fe110-adsorption-role-runtime-cpu-tested-20261019"
    event_id = "task-fe110-adsorption-training-comparison-prepared-20261019"
    paths = ["docs/reviews/fe110_adsorption_training_comparison_20261019.md",
             "archive/fe110_adsorption_training_comparison_20261019/request_scope.md"]
    paths += [(OUTPUT / name).relative_to(ROOT).as_posix() for name in
              ("comparison_request.json", "verification_receipt.json", "validation_commands.json", "scoped_tests.xml", "native_cli.json", "native_cli_receipt.json")]
    evidence = [{"locator": path, "sha256": sha256_file(ROOT / path), "authority": "user_authorization" if path.endswith("request_scope.md")
                 else "repository_document", "observed_at": now} for path in paths]
    event = {"schema_version": 1, "event_id": event_id, "occurred_at": now, "recorded_at": now,
        "event_type": "task_updated", "entity": {"kind": "task", "id": "task-current", "module": "adsorption_workflow"},
        "summary": "Prepared two hash-bound role-runtime-v3 training comparison arms;137tests and RAM-only nativeCLI checks passed.No GPU execution or scientific promotion.",
        "evidence": evidence, "review": {"required": False, "reason_codes": [], "status": "not_required"}, "supersedes": [prior],
        "payload": {"objective": "Review bounded adsorption force-training comparison;execute GPU only after separate exact-hash user authorization.",
            "phase": "verification", "current_evidence": [
                "Prepared comparison SHA f5db5cb7b1e98d6153bba8bbc41a0d0697fd29c79162a4ef0298a91969660987:control dbad960b964805277333d21bce0a1669e38085c9ab742f5ed53a88a9a5b2d026;treatment 8b740e698d2bac32bb9f918012372a1aaf4e410d9bfef61397bb55ce95ab69ca.",
                "Both arms freeze originalAQCat25 e1f14d50590102dbdf64491a6ae328df6ba0ca2ebb947fbe72213820ae67eb50,identical248train/60development structures/forces,and common role-aware development epoch selection.Control train weights/probabilities only are derived;original pool and treatment manifest bytes unchanged.",
                "Each arm max2epochs/496optimizersteps/30minutes,oneGPU/4CPU/32GB,seed42,lr1e-5;sequential proposed total60GPUminutes.No automatic retries or promotion.",
                "137scoped tests passed plus compile/Ruff/Bash and independent package hash/label/design checks.NativeMZ73 CLI/config/registry passed using RAM modules;no actual labels uploaded,model loaded,CUDA initialized or remote files written.",
                "Actual native eval_every is optimizer-step cadence;new arms validate/checkpoint once per248step epoch,instead of inherited per-step validation.No actual training or accuracy/speedup result exists."],
            "one_executable_step": "Obtain user review of the two-arm initialization/design/budget,then separate exact-arm-hash deployment/GPU authorization;do not infer execution authority from prepared-package checks.",
            "submission_boundary": "PREPARED_FOR_REVIEW_ONLY:no GPU training/inference,private dataset upload,new VASP,oldjob mutation,model promotion or scientific registration authorized.",
            "done_when": ["Two arms bind identical physical labels/splits/initialization with only reviewed training-weight and sampling differences.",
                "Bounded budget,actual CLI and namespace packaging,raw DB/role alignment and scoped regressions are checked.",
                "Exact request hashes,no-model evidence and remaining GPU/scientific boundaries are provided for user review."],
            "constraints": ["Default/deployed Fairchem and old packages remain unchanged;runtimev3 is explicit opt-in.",
                "Keep46newheldout and16observedheldout outside gradients/epoch choice;integrity reads only,noheldoutDB or model loader.C2H3has test-only coverage.",
                "Common original initialization is a proposal rather than proved better than2185;combined weighting+sampling comparison cannot isolate each component.",
                "Single seed/twoepochs is a bounded experiment,not proof of training convergence or acceleration.O/H/replay regressions are review warnings;no zero-tolerance promotion gate.",
                "On-disk deployment/PYTHONPATH,baseline checkpoint,current scheduler/GPU and full-model AMP/optimizer preflight remain required after authority.Old direct-execution exceptions cannot authorize this package."],
            "authoritative_references": ["configs/execution_backends.yaml", paths[0],
                "scripts/adsorption/force_training_preflight.py", "scripts/adsorption/role_training_job.sh",
                (OUTPUT / "comparison_request.json").relative_to(ROOT).as_posix(),
                (OUTPUT / "verification_receipt.json").relative_to(ROOT).as_posix()]}}
    target = ROOT / "modules/state_handoff/events" / (event_id + ".json")
    write_json_exclusive(target, event)
    print(json.dumps({"event": target.relative_to(ROOT).as_posix(), "sha256": sha256_file(target), "validation_commands": len(results)}))


if __name__ == "__main__":
    main()
