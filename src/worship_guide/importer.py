from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}


def iter_assets(input_path: Path) -> Iterable[Path]:
    if not input_path.exists():
        raise FileNotFoundError(f"입력 경로가 없습니다: {input_path}")

    if input_path.is_file():
        yield from _expand_file(input_path)
        return

    for path in sorted(input_path.rglob("*")):
        if path.is_file():
            yield from _expand_file(path)


def _expand_file(path: Path) -> Iterable[Path]:
    if path.suffix.lower() in SUPPORTED:
        yield path
        return

    if path.suffix.lower() == ".zip":
        try:
            with tempfile.TemporaryDirectory(prefix="wg_zip_") as directory:
                temp_root = Path(directory)
                with zipfile.ZipFile(path) as archive:
                    archive.extractall(temp_root)
                for item in sorted(temp_root.rglob("*")):
                    if item.is_file() and item.suffix.lower() in SUPPORTED:
                        # The generator keeps the temporary directory alive
                        # until the caller consumes or closes the iterator.
                        yield item
        except zipfile.BadZipFile as exc:
            raise ValueError(f"손상된 ZIP 파일입니다: {path}") from exc
