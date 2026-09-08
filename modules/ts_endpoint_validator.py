"""Compatibility alias for :mod:`scripts.ts_endpoint.validator`."""

import sys

from scripts.ts_endpoint import validator as _implementation

sys.modules[__name__] = _implementation
