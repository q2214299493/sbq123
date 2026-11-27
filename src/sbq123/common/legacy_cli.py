"""Explicit entry for historical python -m invocations using an installed role."""

import argparse
import runpy
import sys

from sbq123.common.compat import activate


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("role", choices=("mkm", "kmc"))
    p.add_argument("module")
    p.add_argument("args", nargs=argparse.REMAINDER)
    args = p.parse_args()
    finder = activate(args.role)
    if args.module not in finder.paths:
        raise ValueError("Module outside installed role")
    sys.argv = [args.module, *args.args]
    runpy.run_module(args.module, run_name="__main__", alter_sys=True)


if __name__ == "__main__":
    main()
