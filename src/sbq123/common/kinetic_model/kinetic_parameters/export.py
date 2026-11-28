"""Lazy numerical export entry points; install the distribution for the selected format."""
from .export_contract import per_bar, source_info, validate_export
from sbq123.common.reaction_network.reaction_network.event_geometry import verify_event, verify_pattern


def catkinas(dataset):
    from sbq123.mkm.catkinas.export import catkinas as emit
    return emit(dataset)


def catkinas_energy_pair(forward, reverse, temperature):
    from sbq123.mkm.catkinas.export import catkinas_energy_pair as convert
    return convert(forward, reverse, temperature)


def zacros(dataset):
    from sbq123.kmc.zacros.export import zacros as emit
    return emit(dataset)


__all__ = ["catkinas", "catkinas_energy_pair", "per_bar", "source_info", "validate_export",
           "verify_event", "verify_pattern", "zacros"]
