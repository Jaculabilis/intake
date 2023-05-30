from datetime import datetime
from pathlib import Path
import os

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

    # Get all items
    # TODO: support paging parameters
    all_items = list(source.get_all_items())
    all_items.sort(key=item_sort_key)

    return render_template(
        "feed.jinja2",
        items=all_items,
        now=int(time.time()),
        mdeac=[
            {"source": item["source"], "itemid": item["id"]}
            for item in all_items
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


def wsgi():
    # init_default_logging()
    return app
