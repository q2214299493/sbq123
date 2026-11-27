#!/usr/bin/env python3
from __future__ import annotations

# Compatibility wrapper only.  The packaged module is the single implementation
# and should be invoked with ``python -m scripts.ts_strategy_engine.cli``.

from scripts.ts_strategy_engine.active_learning_cli import main


if __name__ == "__main__":
    main()
