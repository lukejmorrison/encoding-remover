"""Export helpers for clean JSON / CSV output."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_csv_bundle(out_dir: Path, data: dict[str, Any]) -> list[Path]:
    """Write flat CSV tables alongside a capture JSON payload."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    reactions_path = out_dir / "reactions_soc.csv"
    with reactions_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["soc", "count"])
        for r in data.get("reactions", []):
            w.writerow([r["soc"], r["count"]])
    written.append(reactions_path)

    pts_path = out_dir / "preferred_terms.csv"
    with pts_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["soc", "term", "count"])
        for r in data.get("reactions", []):
            for pt in r.get("preferred_terms", []):
                w.writerow([r["soc"], pt["term"], pt["count"]])
    written.append(pts_path)

    for key, filename in (
        ("by_year", "by_year.csv"),
        ("by_age_group", "by_age_group.csv"),
        ("by_sex", "by_sex.csv"),
        ("by_continent", "by_continent.csv"),
    ):
        p = out_dir / filename
        with p.open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["label", "count"])
            for row in data.get(key, []):
                w.writerow([row["label"], row["count"]])
        written.append(p)

    brands_path = out_dir / "brands.csv"
    with brands_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["brand"])
        for b in data.get("brands", []):
            w.writerow([b])
    written.append(brands_path)

    return written
