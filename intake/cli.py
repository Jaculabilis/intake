import os
import sys

def main():
    try:
        print("Hello, world!")
    except BrokenPipeError:
        # See https://docs.python.org/3.10/library/signal.html#note-on-sigpipe
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(1)
