"""Compatibility alias for :mod:`scripts.ts_endpoint.database`."""

import sys

from scripts.ts_endpoint import database as _implementation

sys.modules[__name__] = _implementation
