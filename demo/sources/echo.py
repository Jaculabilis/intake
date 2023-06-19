#!/usr/bin/env python3

import hashlib, json, os, sys

echo = os.environ.get("MESSAGE", "Hello, world!")
item = {
    "id": hashlib.md5(echo.encode("utf8")).hexdigest(),
    "title": echo,
}
print(json.dumps(item), file=sys.stdout)
