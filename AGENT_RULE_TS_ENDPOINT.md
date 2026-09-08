# Mandatory Non-Regression and Integration Constraints

- This is an additive rule change, not a refactor.
- Do not change the existing adsorption-site search, optimizer, VASP-input
  generation, scheduler, legacy routing, or adsorption-database schema.
- Keep all existing public arguments optional and backward compatible.
- Reuse the existing atom mapping, periodic mapping, relaxation evidence,
  reaction-event validator, and path checks.

# TS Endpoint Rule

Version: 1.1

## Stable Product Reuse

A TS task must not use the lowest-energy product as a NEB endpoint before
path-compatibility validation.

The lowest-energy product may be reused directly when all of the following
checks pass:

1. atom mapping;
2. periodic mapping;
3. local stability;
4. the intended reaction event, with no extra independent event;
5. path connectivity.

Being the lowest-energy product is neither an automatic rejection nor an
automatic acceptance.

## Independent TS Endpoint

Generate and store a separate TS endpoint only when:

- the lowest-energy product contains an additional independent reaction event;
- the lowest-energy product fails one of the required checks; or
- a more path-compatible locally stable endpoint exists.

The stable product and TS endpoint may therefore reference the same structure
or different structures. Structure purpose must be explicit; do not infer it
from a filename.

## Selection Priority

1. valid atom mapping;
2. valid periodic mapping;
3. correct target reaction event;
4. no additional independent reaction event;
5. path connectivity;
6. local stability;
7. minimum unnecessary migration;
8. energy.

Energy must not override a failure in any preceding gate.
