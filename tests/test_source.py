import json

from intake.source import fetch_items, update_items, LocalSource


def test_default_source(using_source):
    source: LocalSource = using_source("default")
    fetch = fetch_items(source)
    assert len(fetch) == 0

def test_basic_lifecycle(using_source):
    source: LocalSource = using_source("test_inbox")
    state = {"inbox": [{"id": "first"}]}
    source.get_state_path().write_text(json.dumps(state))

    # The inboxed item is returned from fetch
    fetch = fetch_items(source)
    assert len(fetch) == 1
    assert fetch[0]["id"] == "first"

    # Update creates the item in the source
    update_items(source, fetch)
    assert source.get_item_path("first").exists()
    assert source.get_item("first").get("active") == True
    items = list(source.get_all_items())
    assert len(items) == 1
    assert items[0]["id"] == "first"

    # A second fetch does not change anything
    fetch = fetch_items(source)
    update_items(source, fetch)
    assert source.get_item_path("first").exists()
    assert source.get_item("first").get("active") == True
    items = list(source.get_all_items())
    assert len(items) == 1
    assert items[0]["id"] == "first"

    # The item remains after it is no longer in the feed
    state = {"inbox": [{"id": "second"}]}
    source.get_state_path().write_text(json.dumps(state))

    fetch = fetch_items(source)
    update_items(source, fetch)
    assert source.get_item_path("first").exists()
    assert source.get_item("first").get("active") == True
    assert source.get_item_path("second").exists()
    assert source.get_item("second").get("active") == True
    items = list(source.get_all_items())
    assert len(items) == 2
    assert sorted(map(lambda i: i["id"], items)) == ["first", "second"]

    # The item is removed on the next update when it is inactive
    first = source.get_item("first")
    first["active"] = False
    source.save_item(first)

    fetch = fetch_items(source)
    update_items(source, fetch)
    assert not source.get_item_path("first").exists()
    assert source.get_item_path("second").exists()
    items = list(source.get_all_items())
    assert len(items) == 1
    assert items[0]["id"] == "second"
