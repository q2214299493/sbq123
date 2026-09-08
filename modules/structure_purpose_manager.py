"""Compatibility alias for :mod:`scripts.ts_endpoint.purpose`."""

import sys

from scripts.ts_endpoint import purpose as _implementation

sys.modules[__name__] = _implementation
