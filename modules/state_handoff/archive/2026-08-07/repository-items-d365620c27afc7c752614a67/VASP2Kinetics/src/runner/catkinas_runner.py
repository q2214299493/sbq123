"""CATKINAS external process runner."""

from .base_runner import BaseRunner


class CatkinasRunner(BaseRunner):
    """Run the configured CATKINAS command once."""

    software = "CATKINAS"
