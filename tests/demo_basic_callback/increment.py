#!/usr/bin/env python3

import argparse, json, sys

parser = argparse.ArgumentParser()
parser.add_argument("action")
args = parser.parse_args()

print("args:", args, file=sys.stderr, flush=True)

if args.action == "fetch":
    print(
        json.dumps(
            {
                "id": "updateme",
                "title": "The count is at 1",
                "action": {
                    "increment": 1,
                    "decrement": "",
                },
            }
        )
    )

if args.action == "increment":
    item = sys.stdin.readline()
    item = json.loads(item)
    item["action"]["increment"] += 1
    item["body"] = f"<p>{item['action']['increment']}</p>"
    item["title"] = f"The count is at {item['action']['increment']}"
    print(json.dumps(item))

if args.action == "decrement":
    item = sys.stdin.readline()
    item = json.loads(item)
    item["action"]["increment"] -= 1
    item["body"] = f"<p>{item['action']['increment']}</p>"
    item["title"] = f"The count is at {item['action']['increment']}"
    print(json.dumps(item))
