"""Entrypoints for independently installed mkm workflows."""

from sbq123.common.compat import historical_module


def repo_state():
    return historical_module("mkm", "scripts.state_manager.cli").main()


def registry_promote():
    return historical_module("mkm", "scripts.registry_excel_promotion").main()


def registry_write():
    return historical_module("mkm", "scripts.registry_write").main()


def registry_init():
    return historical_module("mkm", "scripts.init_registry").main()


def ts_strategy():
    return historical_module("mkm", "scripts.ts_strategy_engine.cli").main()


def document_governance():
    return historical_module("mkm", "scripts.document_governance").main()


def capability_readiness():
    return historical_module("mkm", "scripts.generate_capability_readiness").main()


def catalysis_search():
    return historical_module("mkm", "scripts.catalysis_retrieval.cli").main()


def catalysis_validate():
    return historical_module("mkm", "scripts.catalysis_retrieval.validate_cli").main()
