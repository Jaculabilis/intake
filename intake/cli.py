from datetime import datetime
from pathlib import Path
from shutil import get_terminal_size
import argparse
import json
import os
import os.path
import subprocess
import sys

from intake.source import fetch_items, LocalSource, update_items, execute_action
from intake.types import InvalidConfigException, SourceUpdateException


def intake_data_dir() -> Path:
    home = Path(os.environ["HOME"])
    data_home = Path(os.environ.get("XDG_DATA_HOME", home / ".local" / "share"))
    intake_data = data_home / "intake"
    return intake_data


def cmd_edit(cmd_args):
    """Open a source's config for editing."""
    parser = argparse.ArgumentParser(
        prog="intake edit",
        description=cmd_edit.__doc__,
    )
    parser.add_argument(
        "--data",
        "-d",
        default=intake_data_dir(),
        help="Path to the intake data directory",
    )
    parser.add_argument(
        "--source",
        "-s",
        required=True,
        help="Source name to edit",
    )
    args = parser.parse_args(cmd_args)

    editor_cmd = os.environ.get("EDITOR")
    if not editor_cmd:
        print("Cannot edit, no EDITOR set")
        return 1

    data = Path(args.data)
    source_path: Path = data / args.source
    if not source_path.exists():
        yn = input("Source does not exist, create? [yN] ")
        if yn.strip().lower() != "y":
            return 0
        source_path.mkdir()
        with (source_path / "intake.json").open("w") as f:
            json.dump(
                {
                    "fetch": {
                        "exe": "",
                        "args": [],
                    },
                    "action": {},
                    "env": {},
                },
                f,
                indent=2,
            )

    # Make a copy of the config
    source = LocalSource(data, args.source)
    tmp_path = source.source_path / "intake.json.tmp"
    tmp_path.write_text(json.dumps(source.get_config(), indent=2))

    while True:
        # Edit the config
        subprocess.run([editor_cmd, tmp_path])

        # Check if the new config is valid
        try:
            json.load(tmp_path.open())
        except json.JSONDecodeError:
            yn = input("Invalid JSON. Return to editor? [Yn] ")
            if yn.strip().lower() != "n":
                continue
            tmp_path.unlink()
            return 0

        tmp_path.replace(source.source_path / "intake.json")
        break

    return 0


def cmd_update(cmd_args):
    """Fetch items for a source and update it."""
    parser = argparse.ArgumentParser(
        prog="intake update",
        description=cmd_update.__doc__,
    )
    parser.add_argument(
        "--data",
        "-d",
        default=intake_data_dir(),
        help="Path to the intake data directory containing source directories",
    )
    parser.add_argument(
        "--source",
        "-s",
        required=True,
        help="Source name to fetch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Instead of updating the source, print the fetched items",
    )
    args = parser.parse_args(cmd_args)

    source = LocalSource(Path(args.data), args.source)
    try:
        items = fetch_items(source)
        if not args.dry_run:
            update_items(source, items)
        else:
            for item in items:
                print("Item:", item)
    except InvalidConfigException as ex:
        print("Could not fetch", args.source)
        print(ex)
        return 1
    except SourceUpdateException as ex:
        print("Error updating source", args.source)
        print(ex)
        return 1

    return 0


def cmd_action(cmd_args):
    """Execute an action for an item."""
    parser = argparse.ArgumentParser(
        prog="intake action",
        description=cmd_action.__doc__,
    )
    parser.add_argument(
        "--data",
        "-d",
        default=intake_data_dir(),
        help="Path to the intake data directory containing source directories",
    )
    parser.add_argument(
        "--source",
        "-s",
        required=True,
        help="Source name to fetch",
    )
    parser.add_argument(
        "--item",
        "-i",
        required=True,
        help="Item id to perform the action with",
    )
    parser.add_argument(
        "--action",
        "-a",
        required=True,
        help="Action to perform",
    )
    args = parser.parse_args(cmd_args)

    source = LocalSource(Path(args.data), args.source)
    try:
        item = execute_action(source, args.item, args.action, 5)
        print("Item:", item)
    except InvalidConfigException as ex:
        print("Could not fetch", args.source)
        print(ex)
        return 1
    except SourceUpdateException as ex:
        print(
            "Error executing source",
            args.source,
            "item",
            args.item,
            "action",
            args.action,
        )
        print(ex)
        return 1

    return 0


def cmd_feed(cmd_args):
    """Print the current feed."""
    parser = argparse.ArgumentParser(
        prog="intake feed",
        description=cmd_feed.__doc__,
    )
    parser.add_argument(
        "--data",
        "-d",
        default=intake_data_dir(),
        help="Path to the intake data directory",
    )
    parser.add_argument(
        "--sources",
        "-s",
        nargs="+",
        help="Limit feed to these sources",
    )
    parser.add_argument
    args = parser.parse_args(cmd_args)

    data = Path(args.data)
    if not data.exists() and data.is_dir():
        print("Not a directory:", data)
        return 1

    if not args.sources:
        args.sources = [child.name for child in data.iterdir()]

    sources = [
        LocalSource(data, name)
        for name in args.sources
        if (data / name / "intake.json").exists()
    ]
    items = [item for source in sources for item in source.get_all_items()]

    if not items:
        print("Feed is empty")
        return 0

    size = get_terminal_size((80, 20))
    width = min(80, size.columns)

    for item in items:
        title = item["title"] if "title" in item else ""
        titles = [title]
        while len(titles[-1]) > width - 4:
            i = titles[-1][: width - 4].rfind(" ")
            titles = titles[:-1] + [titles[-1][:i].strip(), titles[-1][i:].strip()]
        print("+" + (width - 2) * "-" + "+")
        for title in titles:
            print("| {0:<{1}} |".format(title, width - 4))
        print("|{0:<{1}}|".format("", width - 2))
        info1 = ""
        if "author" in title and item["author"]:
            info1 += item["author"] + "  "
        if "time" in item and item["time"]:
            time_dt = datetime.fromtimestamp(item["time"])
            info1 += time_dt.strftime("%Y-%m-%d %H:%M:%S")
        print("| {0:<{1}} |".format(info1, width - 4))
        created_dt = datetime.fromtimestamp(item["created"])
        created = created_dt.strftime("%Y-%m-%d %H:%M:%S")
        info2 = "{0}  {1}  {2}".format(
            item.get("source", ""), item.get("id", ""), created
        )
        print("| {0:<{1}} |".format(info2, width - 4))
        print("+" + (width - 2) * "-" + "+")
        print()


def cmd_run(cmd_args):
    """Run the default Flask server."""
    parser = argparse.ArgumentParser(
        prog="intake run",
        description=cmd_run.__doc__,
    )
    parser.add_argument(
        "--data",
        "-d",
        default=intake_data_dir(),
        help="Path to the intake data directory containing source directories",
    )
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args(cmd_args)

    try:
        from intake.app import app

        app.run(port=args.port, debug=args.debug)
        return 0
    except Exception as ex:
        print(ex)
        return 1


def cmd_help(_):
    """Print the help text."""
    print_usage()
    return 0


def execute_cli():
    """
    Internal entry point for CLI execution.
    """

    # Collect the commands in this module.
    cli = sys.modules[__name__]
    commands = {
        name[4:]: func for name, func in vars(cli).items() if name.startswith("cmd_")
    }
    names_width = max(map(len, commands.keys()))
    desc_fmt = f"  {{0:<{names_width}}}  {{1}}"
    descriptions = "\n".join(
        [desc_fmt.format(name, func.__doc__) for name, func in commands.items()]
    )

    # Set up the top-level parser
    parser = argparse.ArgumentParser(
        prog="intake",
        description=f"Available commands:\n{descriptions}\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        # add_help=False,
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="help",
        help="The command to execute",
        choices=commands,
        metavar="command",
    )
    parser.add_argument(
        "args", nargs=argparse.REMAINDER, help="Command arguments", metavar="args"
    )

    # Extract the usage print for command_help
    global print_usage
    print_usage = parser.print_help

    args = parser.parse_args()

    # Execute command
    sys.exit(commands[args.command](args.args))


def main():
    """
    Main entry point for CLI execution.
    """
    try:
        execute_cli()
    except BrokenPipeError:
        # See https://docs.python.org/3.10/library/signal.html#note-on-sigpipe
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        sys.exit(1)
