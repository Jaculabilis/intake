#!/usr/bin/env python3

import argparse, json, sys

parser = argparse.ArgumentParser()
parser.add_argument("action")
args = parser.parse_args()

print("args:", args, file=sys.stderr, flush=True)

if args.action == "fetch":
    print(json.dumps({
        "id": "updateme",
        "action": {
            "increment": 1
        }
    }))

if args.action == "increment":
    item = sys.stdin.readline()
    item = json.loads(item)
    item["action"]["increment"] += 1
    item["body"] = f"<p>{item['action']['increment']}</p>"
    print(json.dumps(item))
    pass
