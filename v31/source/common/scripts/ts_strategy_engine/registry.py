"""Legacy TS registry imports; migrate new callers to registry_connection.

Connection implementation is generic; final-energy constants belong to
``ts_validation.barrier_values``. This facade owns no state or decisions.
"""
from scripts.registry_connection import (
    open_registry as open_registry, utc_now as utc_now,
    table_exists as table_exists, require_current_schema as require_current_schema,
)
from scripts.registry_schema import CURRENT_VERSION as CURRENT_VERSION, validate_schema as validate_schema
from scripts.registry_compatibility import compatibility_fingerprint as compatibility_fingerprint
from scripts.ts_validation.barrier_values import (
    ACCEPTED_STATIC_STATUS as ACCEPTED_STATIC_STATUS,
    ACCEPTED_COMPATIBLE_FINAL_ENERGY_STATUS as ACCEPTED_COMPATIBLE_FINAL_ENERGY_STATUS,
    ACCEPTED_FINAL_ENERGY_STATUSES as ACCEPTED_FINAL_ENERGY_STATUSES,
)
