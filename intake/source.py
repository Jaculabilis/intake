from pathlib import Path
from subprocess import Popen, PIPE, TimeoutExpired
from threading import Thread
import json
import os
import os.path

from .types import InvalidConfigException, SourceUpdateException


def read_stdout(process: Popen, outs: list):
    """
    Read the subprocess's stdout into memory.
    This prevents the process from blocking when the pipe fills up.
    """
    while True:
        data = process.stdout.readline()
        if data:
            print(f"[stdout] <{repr(data)}>")
            outs.append(data)
        if process.poll() is not None:
            break


def read_stderr(process: Popen):
    """
    Read the subprocess's stderr stream and pass it to logging.
    This prevents the process from blocking when the pipe fills up.
    """
    while True:
        data = process.stderr.readline()
        if data:
            print(f"[stderr] <{repr(data)}>")
        if process.poll() is not None:
            break


def fetch_items(source_path: Path, update_timeout=60):
    """
    Execute the feed source and return the current feed items.
    Returns a list of feed items on success.
    Throws SourceUpdateException if the feed source update failed.
    """
    # Load the source's config to get its update command
    config_path = source_path / "intake.json"
    with open(config_path, "r", encoding="utf8") as config_file:
        config = json.load(config_file)

    if "fetch" not in config:
        raise InvalidConfigException("Missing exe")

    exe_name = config["fetch"]["exe"]
    exe_args = config["fetch"].get("args", [])

    # Overlay the current env with the config env and intake-provided values
    exe_env = {
        **os.environ.copy(),
        **config.get("env", {}),
        "STATE_PATH": str((source_path / "state").absolute()),
    }

    # Launch the update command
    try:
        process = Popen(
            [exe_name, *exe_args],
            stdout=PIPE,
            stderr=PIPE,
            cwd=source_path,
            env=exe_env,
            encoding="utf8",
        )
    except PermissionError:
        raise SourceUpdateException("command not executable")

    # While the update command is executing, watch its output
    t_stderr = Thread(target=read_stderr, args=(process,), daemon=True)
    t_stderr.start()

    outs = []
    t_stdout = Thread(target=read_stdout, args=(process, outs), daemon=True)
    t_stdout.start()

    # Time out the process if it takes too long
    try:
        process.wait(timeout=update_timeout)
    except TimeoutExpired:
        process.kill()
    t_stdout.join(timeout=1)
    t_stderr.join(timeout=1)

    if process.poll():
        raise SourceUpdateException("return code")

    items = []
    for line in outs:
        try:
            item = json.loads(line)
            items.append(item)
        except json.JSONDecodeError:
            raise SourceUpdateException("invalid json")

    return items
