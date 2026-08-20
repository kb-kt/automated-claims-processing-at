from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Iterable


def ensure_writable_output(path: Path, overwrite: bool) -> None:
    path.mkdir(parents=True, exist_ok=True)
    existing = [item for item in path.iterdir() if item.name != ".gitkeep"]
    if existing and not overwrite:
        raise FileExistsError(
            f"Output directory is not empty: {path}. Pass --overwrite to replace files."
        )
    if existing and overwrite:
        for item in existing:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def write_jsonl(path: Path, records: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")))
            file.write("\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")
