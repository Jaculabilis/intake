from datetime import datetime, timedelta
from pathlib import Path
import json
import os
import time

from flask import Flask, render_template, request, jsonify, abort, redirect, url_for

from intake.source import LocalSource, execute_action

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


def item_sort_key(item):
    item_date = item.get("time", item.get("created", 0))
    return (item_date, item["id"])


@app.template_filter("datetimeformat")
def datetimeformat(value):
    if not value:
        return ""
    dt = datetime.fromtimestamp(value)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


@app.get("/")
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

    return render_template(
        "home.jinja2",
        sources=sources,
    )


@app.get("/source/<string:source_name>")
def source_feed(source_name):
    """
    Feed view for a single source.
    """
    source = LocalSource(intake_data_dir(), source_name)
    if not source.source_path.exists():
        abort(404)

    # Get all items
    all_items = sorted(source.get_all_items(), key=item_sort_key)

    # Apply paging parameters
    count = int(request.args.get("count", "100"))
    page = int(request.args.get("page", "0"))
    paged_items = all_items[count * page : count * page + count]
    pager_prev = (
        None
        if page <= 0
        else url_for(
            request.endpoint, source_name=source_name, count=count, page=page - 1
        )
    )
    pager_next = (
        None
        if (count * page + count) > len(all_items)
        else url_for(
            request.endpoint, source_name=source_name, count=count, page=page + 1
        )
    )

    return render_template(
        "feed.jinja2",
        items=paged_items,
        now=int(time.time()),
        mdeac=[
            {"source": item["source"], "itemid": item["id"]}
            for item in paged_items
            if "id" in item
        ],
        pager_prev=pager_prev,
        pager_next=pager_next,
    )


@app.delete("/item/<string:source_name>/<string:item_id>")
def deactivate(source_name, item_id):
    source = LocalSource(intake_data_dir(), source_name)
    item = source.get_item(item_id)
    if item["active"]:
        print(f"Deactivating {source_name}/{item_id}")
    item["active"] = False
    source.save_item(item)
    return jsonify({"active": item["active"]})


@app.patch("/item/<string:source_name>/<string:item_id>")
def update(source_name, item_id):
    source = LocalSource(intake_data_dir(), source_name)
    item = source.get_item(item_id)
    params = request.get_json()
    if "tts" in params:
        tomorrow = datetime.now() + timedelta(days=1)
        morning = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 6, 0, 0)
        til_then = morning.timestamp() - item["created"]
        item["tts"] = til_then
    source.save_item(item)
    return jsonify(item)


@app.post("/mass-deactivate/")
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
def action(source_name, item_id, action):
    source = LocalSource(intake_data_dir(), source_name)
    item = execute_action(source, item_id, action)
    return jsonify(item)


@app.route("/edit/source/<string:source_name>", methods=["GET", "POST"])
def source_edit(source_name):
    """
    Config editor for a source
    """
    source = LocalSource(intake_data_dir(), source_name)
    if not source.source_path.exists():
        abort(404)

    # For POST, check if the config is valid
    error_message: str = None
    if request.method == "POST":
        config_str = request.form.get("config", "")
        error_message, config = try_parse_config(config_str)
        print(config_str)
        print(error_message)
        print(config)
        if not error_message:
            source.save_config(config)
            return redirect(url_for("root"))

    # For GET, load the config
    if request.method == "GET":
        config = source.get_config()
        config_str = json.dumps(config, indent=2)

    return render_template(
        "edit.jinja2",
        source=source,
        config=config_str,
        error_message=error_message,
    )


def try_parse_config(config_str: str):
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
    return (
        None,
        {
            "action": parsed["action"],
            "env": parsed["env"],
        },
    )


def wsgi():
    # init_default_logging()
    return app
