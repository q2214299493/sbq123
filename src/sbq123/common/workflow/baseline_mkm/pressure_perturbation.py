"""Decimal pressure checks for an explicit fixed-total composition grid."""

from decimal import Decimal
from math import log

from sbq123.common.validation.scientific_validation import finite_number


def checked_feed(parent, target, selected, total_bar):
    if target.keys() != parent.keys() or selected not in parent or len(parent) < 2:
        raise ValueError("Composition grid must cover the complete gas inventory")
    def decimals(values):
        return {k: Decimal(str(finite_number(v, "component pressure", positive=True))) for k, v in values.items()}

    before, after = decimals(parent), decimals(target)
    total = Decimal(str(total_bar))
    if sum(before.values()) != total or sum(after.values()) != total:
        raise ValueError("Composition pressures must sum to the exact approved total")
    for k in parent.keys() - {selected}:
        if after[k] * (total - before[selected]) != before[k] * (total - after[selected]):
            raise ValueError("Composition grid changed the remaining gas proportions")
    return log(target[selected] / parent[selected])


def log_order(pressures, rates):
    """Slope at the baseline of the quadratic interpolant on the actual signed log grid."""
    pm, p0, pp = (finite_number(v, "MAT pressure", positive=True) for v in pressures)
    rm, r0, rp = (log(finite_number(v, "overall turnover", positive=True)) for v in rates)
    xm, xp = log(pm / p0), log(pp / p0)
    if not xm < 0 < xp:
        raise ValueError("Actual pressures must bracket the baseline")
    left, right = (rm - r0) / xm, (rp - r0) / xp
    return dict(x_minus=xm, x_plus=xp, negative_side=left, positive_side=right,
                secant=(rp - rm) / (xp - xm), quadratic_at_zero=(xp * left - xm * right) / (xp - xm))
