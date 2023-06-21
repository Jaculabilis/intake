from pathlib import Path
import os


def intake_data_dir() -> Path:
    if intake_data := os.environ.get("INTAKE_DATA"):
        return Path(intake_data)
    if xdg_data_home := os.environ.get("XDG_DATA_HOME"):
        return Path(xdg_data_home) / "intake"
    if home := os.environ.get("HOME"):
        return Path(home) / ".local" / "share" / "intake"
    raise Exception("No intake data directory defined")
