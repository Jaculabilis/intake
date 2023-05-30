from datetime import datetime, timedelta
from pathlib import Path
import os
import time

from flask import Flask, render_template, request, jsonify, abort, redirect, url_for

from intake.source import LocalSource

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


@app.route("/")
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


@app.route("/source/<string:source_name>")
def source_feed(source_name):
    """
    Feed view for a single source.
    """
    source = LocalSource(intake_data_dir(), source_name)
    if not source.source_path.exists():
        abort(404)

    # Get all items
    all_items = source.get_all_items()
    sorted_items = sorted(all_items, key=item_sort_key)

    if count_arg := request.args.get("count"):
        page_arg = request.args.get("page", "0")
        if count_arg.isdigit() and page_arg.isdigit():
            count = int(count_arg)
            page = int(page_arg)
            sorted_items = sorted_items[count * page:count * page + count]

    return render_template(
        "feed.jinja2",
        items=sorted_items,
        now=int(time.time()),
        mdeac=[
            {"source": item["source"], "itemid": item["id"]}
            for item in sorted_items
            if "id" in item
        ],
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


def wsgi():
    # init_default_logging()
    return app
