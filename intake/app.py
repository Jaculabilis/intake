from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from random import getrandbits
from typing import List
import json
import os
import time

from flask import Flask, render_template, request, jsonify, abort, redirect, url_for

from intake.source import LocalSource, execute_action, Item

# Globals
app = Flask(__name__)


def intake_data_dir() -> Path:
    if intake_data := os.environ.get("INTAKE_DATA"):
        return Path(intake_data)
    if xdg_data_home := os.environ.get("XDG_DATA_HOME"):
        return Path(xdg_data_home) / "intake"
    if home := os.environ.get("HOME"):
        return Path(home) / ".local" / "share" / "intake"
    raise Exception("No intake data directory defined")


def item_sort_key(item: Item):
    return item.sort_key


@app.template_filter("datetimeformat")
def datetimeformat(value):
    if not value:
        return ""
    dt = datetime.fromtimestamp(value)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def auth_check(route):
    """
    Checks the HTTP Basic Auth header against the stored credential.
    """

    @wraps(route)
    def _route(*args, **kwargs):
        data_path = intake_data_dir()
        auth_path = data_path / "credentials.json"
        if auth_path.exists():
            if not request.authorization:
                abort(401)
            auth = json.load(auth_path.open(encoding="utf8"))
            if request.authorization.username != auth["username"]:
                abort(403)
            if request.authorization.password != auth["secret"]:
                abort(403)
        return route(*args, **kwargs)

    return _route


@app.get("/")
@auth_check
def root():
    """
    Navigation home page.
    """
    data_path = intake_data_dir()

    sources = []
    for child in data_path.iterdir():
        if (child / "intake.json").exists():
            sources.append(LocalSource(data_path, child.name))
    sources.sort(key=lambda s: s.source_name)

    channels = {}
    channels_config_path = data_path / "channels.json"
    if channels_config_path.exists():
        channels = json.loads(channels_config_path.read_text(encoding="utf8"))

    return render_template(
        "home.jinja2",
        sources=sources,
        channels=channels,
    )


@app.get("/source/<string:name>")
@auth_check
def source_feed(name):
    """
    Feed view for a single source.
    """
    source = LocalSource(intake_data_dir(), name)
    if not source.source_path.exists():
        abort(404)

    return _sources_feed(name, [source], show_hidden=request.args.get("hidden", True))


@app.get("/channel/<string:name>")
@auth_check
def channel_feed(name):
    """
    Feed view for a channel.
    """
    channels_config_path = intake_data_dir() / "channels.json"
    if not channels_config_path.exists():
        abort(404)
    channels = json.loads(channels_config_path.read_text(encoding="utf8"))
    if name not in channels:
        abort(404)
    sources = [LocalSource(intake_data_dir(), name) for name in channels[name]]

    return _sources_feed(name, sources, show_hidden=request.args.get("hidden", False))


def _sources_feed(name: str, sources: List[LocalSource], show_hidden: bool):
    """
    Feed view for multiple sources.
    """
    # Get all items
    all_items = sorted(
        [
            item
            for source in sources
            for item in source.get_all_items()
            if not item.is_hidden or show_hidden
        ],
        key=item_sort_key,
    )

    # Apply paging parameters
    count = int(request.args.get("count", "100"))
    page = int(request.args.get("page", "0"))
    paged_items = all_items[count * page : count * page + count]
    pager_prev = (
        None
        if page <= 0
        else url_for(request.endpoint, name=name, count=count, page=page - 1)
    )
    pager_next = (
        None
        if (count * page + count) > len(all_items)
        else url_for(request.endpoint, name=name, count=count, page=page + 1)
    )

    return render_template(
        "feed.jinja2",
        items=paged_items,
        now=int(time.time()),
        mdeac=[
            {"source": item.source.source_name, "itemid": item["id"]}
            for item in paged_items
            if "id" in item
        ],
        pager_prev=pager_prev,
        pager_next=pager_next,
    )


@app.delete("/item/<string:source_name>/<string:item_id>")
@auth_check
def deactivate(source_name, item_id):
    source = LocalSource(intake_data_dir(), source_name)
    item = source.get_item(item_id)
    if item["active"]:
        print(f"Deactivating {source_name}/{item_id}")
    item["active"] = False
    source.save_item(item)
    return jsonify({"active": item["active"]})


@app.patch("/item/<string:source_name>/<string:item_id>")
@auth_check
def update(source_name, item_id):
    source = LocalSource(intake_data_dir(), source_name)
    item = source.get_item(item_id)
    params = request.get_json()
    if "tts" in params:
        tomorrow = datetime.now() + timedelta(days=1)
        morning = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 6, 0, 0)
        til_then = int(morning.timestamp()) - item["created"]
        item["tts"] = til_then
    source.save_item(item)
    return jsonify(item._item)


@app.post("/mass-deactivate/")
@auth_check
def mass_deactivate():
    params = request.get_json()
    if "items" not in params:
        print(f"Bad request params: {params}")
    for info in params.get("items"):
        source = info["source"]
        itemid = info["itemid"]
        source = LocalSource(intake_data_dir(), source)
        item = source.get_item(itemid)
        if item["active"]:
            print(f"Deactivating {info['source']}/{info['itemid']}")
        item["active"] = False
        source.save_item(item)
    return jsonify({})


@app.post("/action/<string:source_name>/<string:item_id>/<string:action>")
@auth_check
def action(source_name, item_id, action):
    source = LocalSource(intake_data_dir(), source_name)
    item = execute_action(source, item_id, action)
    return jsonify(item)


@app.route("/edit/source/<string:name>", methods=["GET", "POST"])
@auth_check
def source_edit(name):
    """
    Config editor for a source
    """
    source = LocalSource(intake_data_dir(), name)
    if not source.source_path.exists():
        abort(404)

    # For POST, check if the config is valid
    error_message: str = None
    if request.method == "POST":
        config_str = request.form.get("config", "")
        error_message, config = _parse_source_config(config_str)
        if not error_message:
            source.save_config(config)
            return redirect(url_for("root"))

    # For GET, load the config
    if request.method == "GET":
        config = source.get_config()
        config_str = json.dumps(config, indent=2)

    return render_template(
        "edit.jinja2",
        subtitle=source.source_name,
        config=config_str,
        error_message=error_message,
    )


def _parse_source_config(config_str: str):
    if not config_str:
        return ("Config required", {})
    try:
        parsed = json.loads(config_str)
    except json.JSONDecodeError:
        return ("Invalid JSON", {})
    if not isinstance(parsed, dict):
        return ("Invalid config format", {})
    if "action" not in parsed:
        return ("No actions defined", {})
    action = parsed["action"]
    if "fetch" not in action:
        return ("No fetch action defined", {})
    fetch = action["fetch"]
    if "exe" not in fetch:
        return ("No fetch exe", {})
    config = {"action": parsed["action"]}
    if "env" in parsed:
        config["env"] = parsed["env"]
    return (None, config)


@app.route("/edit/channels", methods=["GET", "POST"])
@auth_check
def channels_edit():
    """
    Config editor for channels
    """
    config_path = intake_data_dir() / "channels.json"

    # For POST, check if the config is valid
    error_message: str = None
    if request.method == "POST":
        config_str = request.form.get("config", "")
        error_message, config = _parse_channels_config(config_str)
        if not error_message:
            config_path.write_text(json.dumps(config, indent=2), encoding="utf8")
            return redirect(url_for("root"))

    # For GET, load the config
    if request.method == "GET":
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf8"))
        else:
            config = {}
        config_str = json.dumps(config, indent=2)

    return render_template(
        "edit.jinja2",
        subtitle="Channels",
        config=config_str,
        error_message=error_message,
    )


def _parse_channels_config(config_str: str):
    if not config_str:
        return ("Config required", {})
    try:
        parsed = json.loads(config_str)
    except json.JSONDecodeError:
        return ("Invalid JSON", {})
    if not isinstance(parsed, dict):
        return ("Invalid config format", {})
    for key in parsed:
        if not isinstance(parsed[key], list):
            return (f"{key} must map to a list", {})
        for val in parsed[key]:
            if not isinstance(val, str):
                return f"{key} source {val} must be a string"
    return (None, parsed)


@app.post("/add")
@auth_check
def add_item():
    # Ensure the default source exists
    source_path = intake_data_dir() / "default"
    if not source_path.exists():
        source_path.mkdir()
    config_path = source_path / "intake.json"
    if not config_path.exists():
        config_path.write_text(
            json.dumps({"action": {"fetch": {"exe": "true"}}}, indent=2)
        )
    source = LocalSource(source_path.parent, source_path.name)

    # Clean up the fields
    fields = {key: value for key, value in request.form.items() if value}
    fields["id"] = "{:x}".format(getrandbits(16 * 4))
    # TODO: this doesn't support tags or ttX fields correctly
    item = Item.create(source, **fields)
    source.save_item(item)

    return redirect(url_for("source_feed", name="default"))


def wsgi():
    # init_default_logging()
    return app
