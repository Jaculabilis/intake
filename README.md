# intake

`intake` is an arbitrary feed aggregator.

## Feed Source Interface

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
  "fetch": {
    "exe": "<absolute path to program or name on intake's PATH>",
    "args": ["list", "of", "program", "arguments"]
  },
  "action": {
    "<action name>": {
      "exe": "...",
      "args": "..."
    }
  },
  "env": { ... }
}
```

`fetch` is required. If `action` or `env` are absent, they will be treated as if they were empty.

When a feed source is updated, `fetch.exe` will be executed with `fetch.args` as arguments. The following environment variables will be set:

* `STATE_PATH` is set to the absolute path of `state`.
* Each key in `env` in `config.json` is passed with its value.

Each line written to the process's `stdout` will be parsed as a JSON object representing a feed item. Each line written to `stderr` will be logged by intake. `stdout` and `stderr` are decoded as UTF-8.

If invalid JSON is written, intake will consider the feed update to be a failure. If the exit code is nonzero, intake will consider the feed update to be a failure, even if valid JSON was received. No changes will happen to the feed state as a result of a failed update.

Item actions are performed by executing `action.<name>.exe` with `action.<name>.args` as arguments. The process will receive the item, serialized as JSON, on the first line of `stdin`. The process should write the item back to `stdout` as a single line of JSON with any updates from the action.
