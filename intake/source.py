from datetime import timedelta
from pathlib import Path
from subprocess import Popen, PIPE, TimeoutExpired
from threading import Thread
from typing import List
import json
import os
import os.path
import time

from intake.types import InvalidConfigException, SourceUpdateException


class LocalSource:
    """
    An intake source backed by a filesystem directory.
    """

    def __init__(self, data_path: Path, source_name: str):
        self.data_path: Path = data_path
        self.source_name = source_name
        self.source_path: Path = data_path / source_name

    def get_config(self) -> dict:
        config_path = self.source_path / "intake.json"
        with open(config_path, "r", encoding="utf8") as config_file:
            return json.load(config_file)

    def get_state_path(self) -> Path:
        return (self.source_path / "state").absolute()

    def get_item_path(self, item_id: dict) -> Path:
        return self.source_path / f"{item_id}.item"

    def get_item_ids(self) -> List[str]:
        return [
            filepath.name[:-5]
            for filepath in self.source_path.iterdir()
            if filepath.name.endswith(".item")
        ]

    def item_exists(self, item_id) -> bool:
        return self.get_item_path(item_id).exists()

    def new_item(self, item: dict) -> dict:
        # Ensure required fields
        if "id" not in item:
            raise KeyError("id")
        item["source"] = self.source_name
        item["active"] = True
        item["created"] = int(time.time())
        item["title"] = item.get("title", item["id"])
        item["tags"] = item.get("tags", [self.source_name])
        # All other fields are optiona
        self.save_item(item)
        return item

    def get_item(self, item_id: str) -> dict:
        with self.get_item_path(item_id).open() as f:
            return json.load(f)

    def save_item(self, item: dict) -> None:
        # Write to a tempfile first to avoid losing the item on write failure
        tmp_path = self.source_path / f"{item['id']}.item.tmp"
        with tmp_path.open("w") as f:
            f.write(json.dumps(item, indent=2))
        os.rename(tmp_path, self.get_item_path(item["id"]))

    def delete_item(self, item_id) -> None:
        os.remove(self.get_item_path(item_id))

    def get_all_items(self) -> List[dict]:
        for filepath in self.source_path.iterdir():
            if filepath.name.endswith(".item"):
                yield json.loads(filepath.read_text(encoding="utf8"))


def read_stdout(process: Popen, output: list):
    """
    Read the subprocess's stdout into memory.
    This prevents the process from blocking when the pipe fills up.
    """
    while True:
        data = process.stdout.readline()
        if data:
            print(f"[stdout] <{repr(data)}>")
            output.append(data)
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


def execute_source_action(
    source: LocalSource, action: str, input: str, timeout: timedelta
):
    """
    Execute the action from a given source. If stdin is specified, pass it
    along to the process.
    """
    # Gather the information necessary to launch the process
    config = source.get_config()
    action_cfg = config.get("action", {}).get(action)

    if not action_cfg:
        raise InvalidConfigException(f"No such action {action}")
    if "exe" not in action_cfg:
        raise InvalidConfigException(f"No exe for action {action}")

    command = [action_cfg["exe"], *action_cfg.get("args", [])]
    env = {
        **os.environ.copy(),
        **config.get("env", {}),
        "STATE_PATH": str(source.get_state_path()),
    }

    # Launch the process
    try:
        process = Popen(
            command,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
            cwd=source.source_path,
            env=env,
            encoding="utf8",
        )
    except PermissionError:
        raise SourceUpdateException(f"Command not executable: {''.join(command)}")

    # Kick off monitoring threads
    output = []
    t_stdout: Thread = Thread(target=read_stdout, args=(process, output), daemon=True)
    t_stdout.start()
    t_stderr: Thread = Thread(target=read_stderr, args=(process,), daemon=True)
    t_stderr.start()

    # Send input to the process, if provided
    if input:
        process.stdin.write(input)
        if not input.endswith("\n"):
            process.stdin.write("\n")
        process.stdin.flush()

    try:
        process.wait(timeout=timeout.total_seconds())
    except TimeoutExpired:
        process.kill()
    t_stdout.join(timeout=1)
    t_stderr.join(timeout=1)

    if process.poll():
        raise SourceUpdateException(
            f"{source.source_name} {action} failed with code {process.returncode}"
        )

    return output


def fetch_items(source: LocalSource, timeout: int = 60):
    """
    Execute the feed source and return the current feed items.
    Returns a list of feed items on success.
    Throws SourceUpdateException if the feed source update failed.
    """
    items = []

    output = execute_source_action(source, "fetch", None, timedelta(timeout))

    for line in output:
        try:
            item = json.loads(line)
            items.append(item)
        except json.JSONDecodeError:
            raise SourceUpdateException("invalid json")

    return items


def execute_action(source: LocalSource, item_id: str, action: str, timeout: int = 60):
    """
    Execute the action for a feed source.
    """
    item = source.get_item(item_id)

    output = execute_source_action(source, action, json.dumps(item), timedelta(timeout))
    if not output:
        raise SourceUpdateException("no item")

    try:
        item = json.loads(output[0])
        source.save_item(item)
        return item
    except json.JSONDecodeError:
        raise SourceUpdateException("invalid json")


def update_items(source: LocalSource, fetched_items):
    """
    Update the source with a batch of new items, doing creations, updates, and
    deletions as necessary.
    """
    # Get a list of item ids that already existed for this source.
    prior_ids = source.get_item_ids()
    print(f"Found {len(prior_ids)} prior items")

    # Determine which items are new and which are updates.
    new_items = []
    upd_items = []
    for item in fetched_items:
        if source.item_exists(item["id"]):
            upd_items.append(item)
        else:
            new_items.append(item)

    # Write all the new items to the source directory.
    for item in new_items:
        # TODO: support on-create trigger
        source.new_item(item)

    # Update the other items using the fetched items' values.
    for upd_item in upd_items:
        old_item = source.get_item(upd_item["id"])
        for field in (
            "title",
            "tags",
            "link",
            "time",
            "author",
            "body",
            "ttl",
            "ttd",
            "tts",
        ):
            if field in upd_item and old_item[field] != upd_item[field]:
                old_item[field] = upd_item[field]
        if "callback" in upd_item:
            # Because of the way this update happens, any fields that are set
            # in the callback when the item is new will keep their original
            # values, as those values reappear in new_item on subsequent
            # updates.
            old_item["callback"] = {**old_item["callback"], **upd_item["callback"]}

    # Items are removed when they are old (not in the latest fetch) and
    # inactive. Some item fields change this basic behavior.
    del_count = 0
    now = int(time.time())
    upd_ids = [item["id"] for item in upd_items]
    old_item_ids = [item_id for item_id in prior_ids if item_id not in upd_ids]

    for item_id in old_item_ids:
        item = source.get_item(item_id)
        remove = not item["active"]

        # The time-to-live field protects an item from removal until expiry.
        # This is mainly used to avoid old items resurfacing when their source
        # cannot guarantee monotonicity.
        if "ttl" in item:
            ttl_date = item["created"] + item["ttl"]
            if ttl_date > now:
                continue

        # The time-to-die field puts a maximum lifespan on an item, removing it
        # even if it is active.
        if "ttd" in item:
            ttd_date = item["created"] + item["ttd"]
            if ttd_date < now:
                remove = True

        # Items to be removed are deleted.
        if remove:
            source.delete_item(item["id"])
            del_count += 1

    print(len(new_items), "new,", del_count, "deleted")
