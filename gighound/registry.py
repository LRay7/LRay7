from __future__ import annotations

from pathlib import Path

import yaml

from . import config
from .models import Source


def load_sources(sources_dir: Path | None = None) -> list[Source]:
    """Load every source YAML under sources/. Each file holds a list of sources."""
    root = sources_dir or config.SOURCES_DIR
    sources: list[Source] = []
    for path in sorted(root.rglob("*.yaml")):
        with open(path) as f:
            entries = yaml.safe_load(f) or []
        if not isinstance(entries, list):
            raise ValueError(f"{path}: expected a YAML list of sources")
        for entry in entries:
            sources.append(Source(**entry))
    ids = [s.id for s in sources]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate source ids: {sorted(dupes)}")
    return sources


def get_source(source_id: str) -> Source:
    for s in load_sources():
        if s.id == source_id:
            return s
    raise KeyError(f"unknown source: {source_id}")
