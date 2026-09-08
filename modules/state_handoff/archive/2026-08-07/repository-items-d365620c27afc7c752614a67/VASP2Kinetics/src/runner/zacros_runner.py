"""Zacros external process runner."""

from .base_runner import BaseRunner


class ZacrosRunner(BaseRunner):
    """Run the configured Zacros command once."""

    software = "Zacros"
