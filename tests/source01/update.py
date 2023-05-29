#!/usr/bin/env python3

import json
import os
import sys
import time

for i in range(3):
    sys.stderr.write(f"{i+1}...\n")
    sys.stderr.flush()
    time.sleep(1)

item = json.dumps({"id": "helloworld", "title": "Hello = " + os.environ.get("HELLO", "MISSING")})
print(item)
