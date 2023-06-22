from pathlib import Path
import os
import subprocess

from intake.source import LocalSource


INTAKE_CRON_BEGIN = "### begin intake-managed crontab entries"
INTAKE_CRON_END = "### end intake-managed crontab entries"


def get_desired_crons(data_path: Path):
    """
    Get a list of sources and crontab specs from the data directory.
    """
    for child in data_path.iterdir():
        if not (child / "intake.json").exists():
            continue
        source = LocalSource(data_path, child.name)
        config = source.get_config()
        if cron := config.get("cron"):
            yield f"{cron}  . /etc/profile; intake update -s {source.source_name}"


def update_crontab_entries(data_path: Path):
    """
    Update the intake-managed section of the user's crontab.
    """
    # If there is no crontab command available, quit early.
    crontab_exists = subprocess.run(["command", "-v" "crontab"], shell=True)
    if crontab_exists.returncode:
        print("Could not update crontab")
        return

    # Get the current crontab
    get_crontab = subprocess.run(
        ["crontab", "-e"],
        env={**os.environ, "EDITOR": "cat"},
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    crontab_lines = get_crontab.stdout.decode("utf-8").splitlines()

    # Splice the intake crons into the crontab
    new_crontab_lines = []
    section_found = False
    in_section = False
    for i in range(len(crontab_lines)):

        if not section_found and crontab_lines[i] == INTAKE_CRON_BEGIN:
            section_found = True
            in_section = True
            # Open the section and add everything
            new_crontab_lines.append(INTAKE_CRON_BEGIN)
            new_crontab_lines.extend(get_desired_crons(data_path))

        elif crontab_lines[i] == INTAKE_CRON_END:
            new_crontab_lines.append(INTAKE_CRON_END)
            in_section = False

        elif not in_section:
            new_crontab_lines.append(crontab_lines[i])

    # If the splice mark was never found, append the whole section to the end
    if not section_found:
        new_crontab_lines.append(INTAKE_CRON_BEGIN)
        new_crontab_lines.extend(get_desired_crons(data_path))
        new_crontab_lines.append(INTAKE_CRON_END)

    # Save the updated crontab
    new_crontab: bytes = "\n".join(new_crontab_lines).encode("utf8")
    save_crontab = subprocess.Popen(
        ["crontab", "-"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    (stdout, stderr) = save_crontab.communicate(new_crontab)
    for line in stdout.decode("utf8").splitlines():
        print("[stdout]", line)
    for line in stderr.decode("utf8").splitlines():
        print("[stderr]", line)
