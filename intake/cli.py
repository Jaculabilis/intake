from pathlib import Path
import argparse
import json
import os
import os.path
import subprocess
import sys

from .source import fetch_items, LocalSource, update_items
from .types import InvalidConfigException, SourceUpdateException


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
        "--base",
        default=intake_data_dir(),
        help="Path to the intake data directory containing source directories",
    )
    parser.add_argument(
        "--source",
        help="Source name to edit",
    )
    args = parser.parse_args(cmd_args)

    editor_cmd = os.environ.get("EDITOR")
    if not editor_cmd:
        print("Cannot edit, no EDITOR set")
        return 1

    # Make a copy of the config
    source = LocalSource(Path(args.base), args.source)
    tmp_path = source.source_path / "intake.json.tmp"
    tmp_path.write_text(json.dumps(source.get_config(), indent=2))

    # Edit the config
    subprocess.run([editor_cmd, tmp_path])

    # Commit the change if the new config is valid
    try:
        json.load(tmp_path.open())
    except json.JSONDecodeError:
        print("Invalid JSON")
        return 1
    tmp_path.replace(source.source_path / "intake.json")

    return 0


def cmd_update(cmd_args):
    """Fetch items for a source and update it."""
    parser = argparse.ArgumentParser(
        prog="intake update",
        description=cmd_update.__doc__,
    )
    parser.add_argument(
        "--base",
        default=intake_data_dir(),
        help="Path to the intake data directory containing source directories",
    )
    parser.add_argument(
        "--source",
        help="Source name to fetch",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Instead of updating the source, print the fetched items"
    )
    args = parser.parse_args(cmd_args)
    ret = 0

    source = LocalSource(Path(args.base), args.source)
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
        ret = 1
    except SourceUpdateException as ex:
        print("Error updating source", args.source)
        print(ex)
        ret = 1

    return ret


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
