"""Stable, user-owned storage, independent of the checkout and launch directory."""

from __future__ import annotations

import os
import shutil
import sqlite3
import sys
from pathlib import Path


def data_home() -> Path:
    override = os.environ.get("WG_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "WorshipGuide"


def ensure_data_home() -> Path:
    root = data_home()
    for name in ("source", "work", "exports", "backups"):
        (root / name).mkdir(parents=True, exist_ok=True)
    return root


def default_db_path() -> Path:
    return ensure_data_home() / "wgdb.sqlite3"


def adopt_legacy_database() -> Path:
    """Copy (never move/delete) one old database on first launch.

    Ambiguous old databases must be deliberately imported using --db; silently
    choosing between independent user libraries would hide data.
    """
    target = default_db_path()
    if target.exists():
        return target
    package = Path(__file__).resolve().parents[2]
    candidates = {
        p.resolve()
        for p in (
            Path.cwd() / "data/wgdb.sqlite3",
            package / "data/wgdb.sqlite3",
            package.parent / "data/wgdb.sqlite3",
        )
        if p.is_file() and p.resolve() != target.resolve()
    }
    if len(candidates) > 1:
        raise RuntimeError(
            "기존 DB가 여러 개입니다. wg-app --db <기존 DB 경로>로 선택하세요. 원본은 보존됩니다."
        )
    if candidates:
        source = candidates.pop()
        with sqlite3.connect(source) as old, sqlite3.connect(target) as new:
            old.backup(new)
        # Retain referenced folders as well. Migration resolves remaining old
        # relative paths against the original location before any new import.
        for name in ("source", "work", "wg_work", "exports"):
            folder = source.parent / name
            if folder.is_dir():
                shutil.copytree(folder, target.parent / name, dirs_exist_ok=True)
        (target.parent / "legacy_origin.txt").write_text(str(source), encoding="utf-8")
    return target
