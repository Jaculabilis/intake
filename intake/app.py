from datetime import datetime, timedelta
from functools import wraps
from pathlib import Path
from random import getrandbits
from typing import List
import json
import sys
import time

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    abort,
    redirect,
    url_for,
    current_app,
)

from intake.core import intake_data_dir
from intake.crontab import update_crontab_entries
from intake.source import LocalSource, execute_action, Item

# Globals
app = Flask(__name__)


CRON_HELPTEXT = """cron spec:
*  *  *  *  *
+-------------- minute (0 - 59)
   +----------- hour (0 - 23)
      +-------- day of month (1 - 31)
         +----- month (1 - 12)
            +-- day of week (0 Sun - 6 Sat)"""


def item_sort_key(item: Item):
    return item.sort_key


def get_show_hidden(default: bool):
    """
    Get the value of the ?hidden query parameter, with a default value if it is
    absent or set to an unnown value.
    """
    hidden = request.args.get("hidden")
    if hidden == "true":
        return True
    if hidden == "false":
        return False
    return default


@app.template_filter("datetimeformat")
def datetimeformat(value):
    if not value:
        return ""
    dt = datetime.fromtimestamp(value)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@app.template_global()
def set_query(**kwargs):
    """
    Helper function to create a URL plus or minus some query parameters.
    """
    args = request.args.copy()
    for key, val in kwargs.items():
        if val is None and key in args:
            del args[key]
        else:
            args[key] = val
    return url_for(request.endpoint, **request.view_args, **args)


def auth_check(route):
    """
    Checks the HTTP Basic Auth header against the stored credential.
    """

    @wraps(route)
    def _route(*args, **kwargs):
        data_path: Path = current_app.config["INTAKE_DATA"]
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
    data_path: Path = current_app.config["INTAKE_DATA"]

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
    data_path: Path = current_app.config["INTAKE_DATA"]
    source = LocalSource(data_path, name)
    if not source.source_path.exists():
        abort(404)

    return _sources_feed(name, [source], show_hidden=get_show_hidden(True))


@app.get("/channel/<string:name>")
@auth_check
def channel_feed(name):
    """
    Feed view for a channel.
    """
    data_path: Path = current_app.config["INTAKE_DATA"]
    channels_config_path = data_path / "channels.json"
    if not channels_config_path.exists():
        abort(404)
    channels = json.loads(channels_config_path.read_text(encoding="utf8"))
    if name not in channels:
        abort(404)
    sources = [LocalSource(data_path, name) for name in channels[name]]

    return _sources_feed(name, sources, show_hidden=get_show_hidden(False))


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
        page_num=page,
        page_count=count,
        item_count=len(all_items),
    )


@app.delete("/item/<string:source_name>/<string:item_id>")
@auth_check
def deactivate(source_name, item_id):
    data_path: Path = current_app.config["INTAKE_DATA"]
    source = LocalSource(data_path, source_name)
    item = source.get_item(item_id)
    if item["active"]:
        print(f"Deactivating {source_name}/{item_id}", file=sys.stderr)
    item["active"] = False
    source.save_item(item)
    return jsonify({"active": item["active"]})


@app.patch("/item/<string:source_name>/<string:item_id>")
@auth_check
def update(source_name, item_id):
    data_path: Path = current_app.config["INTAKE_DATA"]
    source = LocalSource(data_path, source_name)
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
    data_path: Path = current_app.config["INTAKE_DATA"]
    params = request.get_json()
    if "items" not in params:
        print(f"Bad request params: {params}", file=sys.stderr)
    for info in params.get("items"):
        source = info["source"]
        itemid = info["itemid"]
        source = LocalSource(data_path, source)
        item = source.get_item(itemid)
        if item["active"]:
            print(f"Deactivating {info['source']}/{info['itemid']}", file=sys.stderr)
        item["active"] = False
        source.save_item(item)
    return jsonify({})


@app.post("/action/<string:source_name>/<string:item_id>/<string:action>")
@auth_check
def action(source_name, item_id, action):
    data_path: Path = current_app.config["INTAKE_DATA"]
    source = LocalSource(data_path, source_name)
    item = execute_action(source, item_id, action)
    return jsonify(item)


@app.route("/edit/source/<string:name>", methods=["GET", "POST"])
@auth_check
def source_edit(name):
    """
    Config editor for a source
    """
    data_path: Path = current_app.config["INTAKE_DATA"]
    source = LocalSource(data_path, name)
    if not source.source_path.exists():
        abort(404)

    # For POST, check if the config is valid
    error_message: str = None
    if request.method == "POST":
        config_str = request.form.get("config", "")
        error_message, config = _parse_source_config(config_str)
        if not error_message:
            source.save_config(config)
            update_crontab_entries(data_path)
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
        helptext=CRON_HELPTEXT,
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
    if "cron" in parsed:
        config["cron"] = parsed["cron"]
    return (None, config)


@app.route("/edit/channels", methods=["GET", "POST"])
@auth_check
def channels_edit():
    """
    Config editor for channels
    """
    data_path: Path = current_app.config["INTAKE_DATA"]
    config_path = data_path / "channels.json"

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
    data_path: Path = current_app.config["INTAKE_DATA"]
    source_path = data_path / "default"
    if not source_path.exists():
        source_path.mkdir()
    config_path = source_path / "intake.json"
    if not config_path.exists():
        config_path.write_text(
            json.dumps({"action": {"fetch": {"exe": "true"}}}, indent=2)
        )
    source = LocalSource(source_path.parent, source_path.name)

    fields = {"id": "{:x}".format(getrandbits(16 * 4))}
    if form_title := request.form.get("title"):
        fields["title"] = form_title
    if form_link := request.form.get("link"):
        fields["link"] = form_link
    if form_body := request.form.get("body"):
        fields["body"] = form_body
    if form_tags := request.form.get("tags"):
        fields["tags"] = [tag.strip() for tag in form_tags.split() if tag.strip()]
    if form_tts := request.form.get("tts"):
        fields["tts"] = _get_ttx_for_date(datetime.fromisoformat(form_tts))
    if form_ttl := request.form.get("ttl"):
        fields["ttl"] = _get_ttx_for_date(datetime.fromisoformat(form_ttl))
    if form_ttd := request.form.get("ttd"):
        fields["ttd"] = _get_ttx_for_date(datetime.fromisoformat(form_ttd))

    item = Item.create(source, **fields)
    source.save_item(item)

    return redirect(url_for("source_feed", name="default"))


def _get_ttx_for_date(dt: datetime) -> int:
    """Get the relative time difference between now and a date."""
    ts = int(dt.timestamp())
    now = int(time.time())
    return ts - now


def wsgi():
    app.config["INTAKE_DATA"] = intake_data_dir()
    return app
