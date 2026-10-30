"""Create a separate, nonsecret local entry without replacing previous wrappers."""
from pathlib import Path
import json
import shutil

REPO = Path(__file__).resolve().parents[2]
ROOT = Path(r"C:\Users\86177\Desktop\fe110_rsi_experiments\rsi_runtime_policy_20261030")


def main():
    profile = json.loads((ROOT / "daily_profile.json").read_text(encoding="utf-8"))
    profile["rsi"]["trial_policy_ids"] = ["check_registered_material"]
    with (ROOT / "trial_profile.json").open("x", encoding="utf-8") as handle:
        json.dump(profile, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    wrapper = '''"""Local research entry. Default accepted-only; opt into the bounded trial by profile."""
from pathlib import Path
import sys

REPO = Path(REPO_VALUE)
sys.path.insert(0, str(REPO))
from scripts.research_assistant.cli import main

if __name__ == "__main__":
    args = sys.argv[1:]
    commands = {"run", "resume", "tools", "feedback", "spc-export", "policies", "usage"}
    command = args.pop(0) if args and args[0] in commands else "run"
    profile = ["--profile", str(Path(__file__).with_name("daily_profile.json"))] if command in {"run", "resume"} and "--profile" not in args else []
    sys.argv = [sys.argv[0], command, *profile, *args]
    main()
'''.replace("REPO_VALUE", repr(str(REPO)))
    with (ROOT / "use_research.py").open("x", encoding="utf-8") as handle:
        handle.write(wrapper)
    shutil.copyfile(__file__, ROOT / "create_local_entry.py")
    print("Local accepted-only entry and explicit trial profile created; previous wrappers unchanged.")


if __name__ == "__main__":
    main()
