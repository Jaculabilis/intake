#!/usr/bin/env python3

import json
import os
import sys
import time

greeting = os.environ.get("HELLO", "MISSING")
item = json.dumps({
    "id": "helloworld",
    "title": "Hello = " + greeting
})
sys.stdout.write(item[:10])
sys.stdout.flush()

for i in range(5):
    sys.stderr.write(f"{i+1}...\n")
    sys.stderr.flush()
    time.sleep(1)

sys.stdout.write(item[10:])
