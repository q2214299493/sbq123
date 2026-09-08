"""Compatibility alias for :mod:`scripts.ts_endpoint.generator`."""

import sys

from scripts.ts_endpoint import generator as _implementation

sys.modules[__name__] = _implementation
