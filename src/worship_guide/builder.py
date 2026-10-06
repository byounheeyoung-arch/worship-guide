from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path

from .importer import iter_assets
from .models import ScoreAsset, SongRecord
from .normalize import canonical_title, parse_title_and_key


def scan_assets(input_path: Path) -> list[ScoreAsset]:
    assets: list[ScoreAsset] = []
    for path in iter_assets(input_path):
        title, key, confidence = parse_title_and_key(path.name)
        assets.append(
            ScoreAsset(
                source_path=str(path),
                file_name=path.name,
                extension=path.suffix.lower(),
                detected_title=title,
                detected_key=key,
                confidence=confidence,
            )
        )
    return assets


def build_records(input_path: Path) -> list[SongRecord]:
    grouped: dict[str, list[ScoreAsset]] = defaultdict(list)
    display_titles: dict[str, str] = {}

    for asset in scan_assets(input_path):
        key = canonical_title(asset.detected_title)
        grouped[key].append(asset)
        display_titles.setdefault(key, asset.detected_title)

    records: list[SongRecord] = []
    for index, group_key in enumerate(sorted(grouped, key=lambda k: display_titles[k]), start=1):
        assets = grouped[group_key]
        keys = sorted({a.detected_key for a in assets if a.detected_key}, key=_key_sort)
        confidence = round(sum(a.confidence for a in assets) / len(assets))
        records.append(
            SongRecord(
                wgid=f"WG{index:06d}",
                title=display_titles[group_key],
                available_keys=keys,
                assets=assets,
                confidence=confidence,
            )
        )
    return records


def write_outputs(records: list[SongRecord], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / "songs.json"
    json_path.write_text(
        json.dumps([record.model_dump() for record in records], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    fieldnames = list(records[0].csv_row().keys()) if records else ["WGID", "곡명"]
    with (output_dir / "songs.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(record.csv_row())

    review = [record for record in records if record.confidence < 90 or not record.available_keys]
    with (output_dir / "review_queue.csv").open("w", encoding="utf-8-sig", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        for record in review:
            writer.writerow(record.csv_row())


def _key_sort(key: str) -> tuple[int, int]:
    order = {name: idx for idx, name in enumerate(["C", "D", "E", "F", "G", "A", "B"])}
    accidental_rank = {"b": 0, "": 1, "#": 2}
    return order.get(key[0], 99), accidental_rank.get(key[1:] if len(key) > 1 else "", 9)
