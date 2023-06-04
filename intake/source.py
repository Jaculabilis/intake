from datetime import timedelta
from pathlib import Path
from subprocess import Popen, PIPE, TimeoutExpired
from threading import Thread
from time import time as current_time
from typing import List
import json
import os
import os.path

from intake.types import InvalidConfigException, SourceUpdateException


class Item:
    """
    A wrapper for an item object.
    """

    def __init__(self, source: "LocalSource", item: dict):
        self.source = source
        self._item = item

    # Methods to allow Item as a drop-in replacement for the item dict itself
    def __contains__(self, key):
        return self._item.__contains__(key)

    def __iter__(self):
        return self._item.__iter__

    def __getitem__(self, key):
        return self._item.__getitem__(key)

    def __setitem__(self, key, value):
        return self._item.__setitem__(key, value)

    def get(self, key, default=None):
        return self._item.get(key, default)

    @staticmethod
    def create(source: "LocalSource", **fields) -> "Item":
        if "id" not in fields:
            raise KeyError("id")
        item = {
            "id": fields["id"],
            "source": source.source_name,
            "created": int(current_time()),
            "active": True,
        }
        for field_name in (
            "title",
            "author",
            "body",
            "link",
            "time",
            "tags",
            "tts",
            "ttl",
            "ttd",
            "action",
        ):
            if val := fields.get(field_name):
                item[field_name] = val
        return Item(source, item)

    @property
    def display_title(self):
        return self._item.get("title", self._item["id"])

    @property
    def abs_tts(self):
        if "tts" not in self._item:
            return None
        return self._item["created"] + self._item["tts"]

    @property
    def can_remove(self):
        # The time-to-live fields protects an item from removal until expiry.
        # This is mainly used to avoid old items resurfacing when their source
        # cannot guarantee monotonocity.
        if "ttl" in self._item:
            ttl_date = self._item["created"] + self._item["ttl"]
            if ttl_date > current_time():
                return False

        # The time-to-die field puts a maximum lifespan on an item, removing it
        # even if it is active.
        if "ttd" in self._item:
            ttd_date = self._item["created"] + self._item["ttd"]
            if ttd_date < current_time():
                return True

        return not self._item["active"]

    @property
    def before_tts(self):
        return (
            "tts" in self._item
            and self._item["created"] + self._item["tts"] < current_time()
        )

    @property
    def is_hidden(self):
        return not self._item["active"] or self.before_tts

    @property
    def sort_key(self):
        item_date = self._item.get(
            "time",
            self._item.get(
                "created",
            ),
        )
        return (item_date, self._item["id"])

    def serialize(self, indent=True):
        return json.dumps(self._item, indent=2 if indent else None)

    def update_from(self, updated: "Item") -> None:
        for field in (
            "title",
            "author",
            "body",
            "link",
            "time",
            "tags",
            "tts",
            "ttl",
            "ttd",
        ):
            if field in updated and self[field] != updated[field]:
                self[field] = updated[field]
        # Actions are not updated since the available actions and associated
        # content is left to the action executor to manage.


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

    def save_config(self, config: dict) -> None:
        config_path = self.source_path / "intake.json"
        tmp_path = config_path.with_name(f"{config_path.name}.tmp")
        with tmp_path.open("w") as f:
            f.write(json.dumps(config, indent=2))
        os.rename(tmp_path, config_path)

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

    def get_item(self, item_id: str) -> Item:
        with self.get_item_path(item_id).open() as f:
            return Item(self, json.load(f))

    def save_item(self, item: Item) -> None:
        # Write to a tempfile first to avoid losing the item on write failure
        item_path = self.get_item_path(item["id"])
        tmp_path = item_path.with_name(f"{item_path.name}.tmp")
        with tmp_path.open("w") as f:
            f.write(item.serialize())
        os.rename(tmp_path, item_path)

    def delete_item(self, item_id) -> None:
        os.remove(self.get_item_path(item_id))

    def get_all_items(self) -> List[Item]:
        for filepath in self.source_path.iterdir():
            if filepath.name.endswith(".item"):
                yield Item(self, json.loads(filepath.read_text(encoding="utf8")))


def _read_stdout(process: Popen, output: list) -> None:
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


def _read_stderr(process: Popen) -> None:
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


def _execute_source_action(
    source: LocalSource, action: str, input: str, timeout: timedelta
) -> List[str]:
    """
    Execute the action from a given source. If stdin is specified, pass it
    along to the process. Returns lines from stdout.
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
    t_stdout: Thread = Thread(target=_read_stdout, args=(process, output), daemon=True)
    t_stdout.start()
    t_stderr: Thread = Thread(target=_read_stderr, args=(process,), daemon=True)
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


def fetch_items(source: LocalSource, timeout: int = 60) -> List[dict]:
    """
    Execute the feed source and return the current feed items.
    Returns a list of feed items on success.
    Throws SourceUpdateException if the feed source update failed.
    """
    items = []

    output = _execute_source_action(source, "fetch", None, timedelta(timeout))

    for line in output:
        try:
            item = Item.create(source, **json.loads(line))
            items.append(item)
        except json.JSONDecodeError:
            raise SourceUpdateException("invalid json")

    return items


def execute_action(
    source: LocalSource, item_id: str, action: str, timeout: int = 60
) -> dict:
    """
    Execute the action for a feed source.
    """
    item: Item = source.get_item(item_id)

    output = _execute_source_action(
        source, action, item.serialize(indent=False), timedelta(timeout)
    )
    if not output:
        raise SourceUpdateException("no item")

    try:
        item = Item(source, json.loads(output[0]))
        source.save_item(item)
        return item
    except json.JSONDecodeError:
        raise SourceUpdateException("invalid json")


def update_items(source: LocalSource, fetched_items: List[Item]):
    """
    Update the source with a batch of new items, doing creations, updates, and
    deletions as necessary.
    """
    # Get a list of item ids that already existed for this source.
    prior_ids = source.get_item_ids()
    print(f"Found {len(prior_ids)} prior items")

    # Determine which items are new and which are updates.
    new_items: List[Item] = []
    upd_items: List[Item] = []
    for item in fetched_items:
        if source.item_exists(item["id"]):
            upd_items.append(item)
        else:
            new_items.append(item)

    # Write all the new items to the source directory.
    for item in new_items:
        # TODO: support on-create trigger
        source.save_item(item)

    # Update the other items using the fetched items' values.
    for upd_item in upd_items:
        old_item = source.get_item(upd_item["id"])
        old_item.update_from(upd_item)
        source.save_item(old_item)

    # Items are removed when they are old (not in the latest fetch) and
    # inactive. Some item fields change this basic behavior.
    del_count = 0
    # now = int(current_time())
    upd_ids = [item["id"] for item in upd_items]
    old_item_ids = [item_id for item_id in prior_ids if item_id not in upd_ids]

    for item_id in old_item_ids:
        if source.get_item(item_id).can_remove:
            source.delete_item(item_id)
            del_count += 1

    print(len(new_items), "new,", del_count, "deleted")
