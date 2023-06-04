#!/usr/bin/env python3

"""
A test source that "generates" items by returning them from the state file.
This source exists for unit testing so that unit tests can easily manipulate
what items are returned by writing them to the state file directly.
"""

import argparse, json, os, sys

parser = argparse.ArgumentParser()
parser.add_argument("action")
args = parser.parse_args()
print("args:", args, file=sys.stderr, flush=True)

if args.action == "fetch":
    state_path = os.environ.get("STATE_PATH")
    with open(state_path) as f:
        state = json.load(f)
    for item in state["inbox"]:
        print(json.dumps(item))
