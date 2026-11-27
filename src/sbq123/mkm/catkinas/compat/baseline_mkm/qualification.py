from scripts.baseline_mkm.mapping_scope import MappingBlocked, check_configuration, topology
from scripts.baseline_mkm.sensitivity_inputs import baseline_config, configuration as sensitivity_configuration, reproduce
from scripts.kinetic_parameters.engine import check_version
from scripts.native_model import assemble


class IncompleteKinetics(ValueError):
    def __init__(self, missing):
        super().__init__("Incomplete kinetic dataset")
        self.missing = missing


def qualify(network, dataset, config, *, general=False):
    check_version(network, "network_version")
    check_version(dataset, "dataset_version")
    if dataset["network_version"] != network["network_version"]:
        raise ValueError("Network version differs from dataset")
    rebuilt = reproduce(network, dataset)
    if rebuilt != dataset:
        raise ValueError("Dataset differs from network, source verification or reviewed rates")
    if "sensitivity_perturbation" in dataset and config != sensitivity_configuration(baseline_config(), rebuilt):
        raise ValueError("Feed or conditions differ from the sensitivity derivative")
    missing = {r["reaction_id"]: r["missing"] for r in dataset["reactions"] if not r["export_eligible"]}
    if missing:
        raise IncompleteKinetics(missing)
    if general:
        check_configuration(config)
    elif len(network["catalog"]["sites"]) > 1 or any(
        len(r["definition"].get("phase_ids") or []) > 1 for r in network["reactions"]
    ):
        issues, _ = topology(network)
        if issues:
            raise MappingBlocked(issues)
        check_configuration(config)
    files, adapter = assemble("catkinas", dataset, config, general_network=network if general else None)
    parameter = dataset["reactions"][0]["parameter_set"]
    for key, value in (
        ("temperature_K", parameter["temperature_K"]),
        ("total_pressure_bar", parameter["pressure_Pa"] / 100000),
    ):
        if key in config and config[key] != value:
            raise ValueError(f"Requested {key} differs from reviewed condition")
    return files, adapter
