from pathlib import Path
from typing import List, Callable

import pytest

from intake.source import LocalSource


def clean_source(source_path: Path):
    for item in source_path.iterdir():
        if item.name.endswith(".item"):
            item.unlink()
    (source_path / "state").unlink(missing_ok=True)


@pytest.fixture
def using_source() -> Callable:
    test_data = Path(__file__).parent
    sources: List[Path] = []

    def _using_source(name: str):
        source_path = test_data / name
        clean_source(source_path)
        sources.append(source_path)
        return LocalSource(test_data, name)
    yield _using_source

    for source_path in sources:
        clean_source(source_path)
