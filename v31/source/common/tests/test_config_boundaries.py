from __future__ import annotations

from pathlib import Path

import pytest

from scripts.adsmind_lite.adsmind_common import load_yaml, load_yaml_schema


ROOT = Path(__file__).resolve().parents[1]


def test_example_adsorption_config_loads_as_a_mapping() -> None:
    payload = load_yaml(ROOT / "configs" / "adsmind_lite" / "analysis_rules.yaml")
    assert "site_classification" in payload


def test_non_mapping_yaml_has_a_clear_error(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("- not\n- a\n- mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML root must be a mapping"):
        load_yaml_schema(invalid, required_keys=("version",), error="missing version")
