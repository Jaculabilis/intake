# intake

`intake` is an arbitrary feed aggregator.

## Feed source interface

The base `intake` directory is `$XDG_DATA_HOME/intake`. Each feed source's data is contained within a subdirectory of the base directory. The name of the feed source is the name of the subdirectory.

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

```
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
  "env": { ... }
}
```

Each key under `action` defines an action that can be taken for the source. The `fetch` action is required. `env` is optional. Each key under `env` will be set as an environment variable when executing actions.

When an action is executed, intake executes the `exe` program for the action with the corresponding `args` as arguments. The process's environment is as follows:

* intake's environment is inherited.
* `STATE_PATH` is set to the absolute path of `state`.
* Each key in `env` in `config.json` is passed with its value.

Anything written to `stderr` by the process will be logged by intake.

The `fetch` action is used to fetch the current state of the feed source. It receives no input and should write feed items to `stdout` as JSON objects, each on one line. All other actions are taken in the context of a single item. These actions receive the item as a JSON object on the first line of `stdin`. The process should write the item back to `stdout` with any changes as a result of the action.

An item must have a key under `action` with that action's name to support executing that action for that item. The value under that key may be any JSON structure used to manage the item-specific state.

All encoding is done with UTF-8. If an item cannot be parsed or the exit code of the process is nonzero, intake will consider the action to be a failure. No items or other feed changes will happen as a result of a failed action, except for changes to `state` done by the action process.

## Item fields

An item has the following top-level fields:

* `id`: **Required**. A unique identifier within the scope of the feed source.
* `created`: **Automatic**. The Unix timestamp at which the item was generated. This attribute is automatically populated.
* `active`: **Automatic**. Whether the item is active. Inactive items are not displayed in channels.
* `title`: The title of the item. If an item has no title, `is` is used as a fallback title.
* `author`: An author name associated with the item.
* `body`: Body text of the item as raw HTML. This will be displayed in the item without further processing.
* `link`: A hyperlink associated with the item.
* `time`: A time associated with the item, not necessarily when the item was created. Feeds sort by `time` when it is defined and fall back to `created`.
* `tags`: A list of tags that describe the item. Tags help filter feeds that contain different kinds of content.
* `tts`: The time-to-show of the item. An item with `tts` defined is hidden from channel feeds until the current time is past `created + tts`.
* `ttl`: The time-to-live of the item. An item with `ttl` defined is not deleted by feed updates even if it is inactive if `created + ttl` is in the future.
* `ttd`: The time-to-die of the item. An item with `ttd` defined is deleted by feed updates even if it is active if `created + ttd` is in the past.
* `action`: An object with keys for all supported actions.
