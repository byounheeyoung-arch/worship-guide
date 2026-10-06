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
        temp_root = Path(tempfile.mkdtemp(prefix="wg_zip_"))
        try:
            with zipfile.ZipFile(path) as archive:
                archive.extractall(temp_root)
            for item in sorted(temp_root.rglob("*")):
                if item.is_file() and item.suffix.lower() in SUPPORTED:
                    # 임시 파일은 build 실행 중에만 사용됩니다.
                    yield item
        except zipfile.BadZipFile as exc:
            raise ValueError(f"손상된 ZIP 파일입니다: {path}") from exc
