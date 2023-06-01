#!/usr/bin/env python3

import argparse, json, sys

parser = argparse.ArgumentParser()
parser.add_argument("action")
args = parser.parse_args()

print("args:", args, file=sys.stderr, flush=True)

if args.action == "fetch":
    print(json.dumps({"id": "caller", "action": {"value": 1}}))

if args.action == "increment":
    item = sys.stdin.readline()
    item = json.loads(item)
    item["action"]["value"] += 1
    print(json.dumps(item))
    pass
