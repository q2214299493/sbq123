"""Compatibility alias for :mod:`scripts.ts_endpoint.evidence`."""

import sys

from scripts.ts_endpoint import evidence as _implementation

sys.modules[__name__] = _implementation
