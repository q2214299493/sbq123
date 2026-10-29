"""Use the existing exclusive transport with this task's bound package roots."""
import argparse

from archive.fe110_scratch512_20261028 import speed_transport as owner
from .prepare import OUTPUT, PACKAGE, POLICY, REMOTE

owner.OUTPUT, owner.PACKAGE, owner.POLICY, owner.REMOTE = OUTPUT, PACKAGE, POLICY, REMOTE


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["upload", "preflight", "launch", "collect"])
    args = parser.parse_args()
    if args.action == "upload":
        owner.upload()
    elif args.action == "collect":
        owner.collect("collection")
    else:
        owner.module(args.action)
