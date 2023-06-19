# intake

Intake is an arbitrary feed aggregator that generalizes the concept of a feed. Rather than being restricted to parsing items out of an RSS feed, Intake provides a middle layer of executing arbitrary programs that conform to a JSON-based specification. An Intake source can parse an RSS feed, but it can also scrape a website without a feed, provide additional logic to filter or annotate feed items, or integrate with an API.

A basic demonstration in a VM can be run with `nixos-shell` using the `#demo` flake attribute.

## Feed source definitions

The base Intake directory is `$XDG_DATA_HOME/intake`. Each feed source's data is contained within a subdirectory of the base directory. The name of the feed source is the name of the subdirectory.

Feed source directories have the following structure:

```
intake
 |- <source name>
 |   |- intake.json
 |   |- state
 |   |- <item id>.item
 |   |- <item id>.item
 |   |- ...
 |- <source name>
 |   |  ...
 | ...
```

`intake.json` must be present; the other files are optional. Each `.item` file contains the data for one feed item. `state` provides a file for the feed source to write arbitrary data, e.g. JSON or binary data.

`intake.json` has the following structure:

```json
{
  "action": {
    "fetch": {
      "exe": "<absolute path to program or name on intake's PATH>",
      "args": ["list", "of", "program", "arguments"]
    },
    "<action name>": {
      "exe": "...",
      "args": "..."
    }
  },
  "env": {
    "...": "..."
  }
}
```

Each key under `action` defines an action that can be taken for the source. `action` must be present with a `fetch` action. `env` is optional.

## Interface for source programs

Intake interacts with sources by executing the actions defined in the source's `intake.json`. The `fetch` action is required and used to check for new feed items.

When any action is executed, intake executes the `exe` program for the action with the corresponding `args` as arguments. The process's working directory is set to the source's folder, i.e. the folder containing `intake.json`. The process's environment is as follows:

* intake's environment is inherited.
* `STATE_PATH` is set to the absolute path of `state`.
* Each key in `env` in `config.json` is passed with its value.

Anything written to `stderr` by the process will be captured and logged by Intake.

The `fetch` action is used to fetch the current state of the feed source. It receives no input and should write feed items to `stdout` as JSON objects, each on one line. All other actions are taken in the context of a single item. These actions receive the item as a JSON object on the first line of `stdin`. The process should write the item back to `stdout` with any changes as a result of the action.

An item must have a key under `action` with that action's name to support executing that action for that item. The value under that key may be any JSON structure used to manage the item-specific state.

All encoding is done with UTF-8. If an item cannot be parsed or the exit code of the process is nonzero, Intake will consider the action to be a failure. No items or other feed changes will happen as a result of a failed action, except for changes to `state` done by the action process.

## Top-level item fields

| Field name | Specification | Description |
| ---------- | ------------- | ----------- |
| `id`       | **Required**  | A unique identifier within the scope of the feed source. |
| `created`  | **Automatic** | The Unix timestamp at which intake first processed the item. |
| `active`   | **Automatic** | Whether the item is active. Inactive items are not displayed in channels. |
| `title`    | Optional      | The title of the item. If an item has no title, `id` is used as a fallback title.
| `author`   | Optional      | An author name associated with the item. Displayed in the item footer.
| `body`     | Optional      | Body text of the item as raw HTML. This will be displayed in the item without further processing! Consider your sources' threat models against injection attacks.
| `link`     | Optional      | A hyperlink associated with the item.
| `time`     | Optional      | A time associated with the item, not necessarily when the item was created. Feeds sort by `time` when it is defined and fall back to `created`. Displayed in the item footer.
| `tags`     | Optional      | A list of tags that describe the item. Tags help filter feeds that contain different kinds of content.
| `tts`      | Optional      | The time-to-show of the item. An item with `tts` defined is hidden from channel feeds until the current time is after `created + tts`.
| `ttl`      | Optional      | The time-to-live of the item. An item with `ttl` defined is not deleted by feed updates as long as `created + ttl` is in the future, even if it is inactive.
| `ttd`      | Optional      | The time-to-die of the item. An item with `ttd` defined is deleted by feed updates if `created + ttd` is in the past, even if it is active.
| `action`   | Optional      | An object with keys for all supported actions. The schema of the values depends on the source.
