from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_slurm_tmpdir_is_overridden_before_setup():
    wrapper = (ROOT / "scripts/adsorption/adsorption_finetune_job.sh").read_text(encoding="utf-8")
    assert wrapper.index('export TMPDIR="$RUN_ROOT/tmp"') < wrapper.index('aqcat25_setup_mz73_environment "$RUN_ROOT"')
    assert '#SBATCH --no-requeue' in wrapper


def test_bootstrap_guard_is_installed_before_checks():
    wrapper = (ROOT / "scripts/adsorption/adsorption_finetune_job.sh").read_text(encoding="utf-8")
    assert wrapper.index("aqcat25_install_bootstrap_guard") < wrapper.index('aqcat25_require_remote_path "$PACKAGE_ROOT" "$AUTHORIZATION"')


def test_bootstrap_prefix_contains_no_model_or_python_run():
    wrapper = (ROOT / "scripts/adsorption/adsorption_finetune_job.sh").read_text(encoding="utf-8")
    prefix = wrapper.split("EXIT_RECORD=", 1)[0]
    assert '"$AQCAT_PYTHON"' not in prefix
    assert "fairchem" not in prefix
    assert "warm-start" not in prefix
    assert 'export TMPDIR="$RUN_ROOT/tmp"' in prefix
