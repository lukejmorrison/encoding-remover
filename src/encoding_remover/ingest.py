"""Ingest capture JSON into the local data catalog for the PWA."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from encoding_remover.export import write_json

DEFAULT_DATA_DIR = Path("data")


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-") or "drug"


def catalog_path(data_dir: Path) -> Path:
    return data_dir / "catalog.json"


def drugs_dir(data_dir: Path) -> Path:
    return data_dir / "drugs"


def load_catalog(data_dir: Path) -> dict[str, Any]:
    path = catalog_path(data_dir)
    if not path.exists():
        return {"version": 1, "drugs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_catalog(data_dir: Path, catalog: dict[str, Any]) -> None:
    write_json(catalog_path(data_dir), catalog)


def entry_from_capture(slug: str, data: dict[str, Any]) -> dict[str, Any]:
    drug = data.get("drug") or {}
    pt_count = sum(
        len(r.get("preferred_terms") or []) for r in data.get("reactions") or []
    )
    return {
        "slug": slug,
        "name": drug.get("name") or data.get("query") or slug,
        "trade_name": drug.get("trade_name"),
        "total_reports": data.get("total_reports", 0),
        "dataset_date": data.get("dataset_date"),
        "retrieved_at": data.get("retrieved_at"),
        "soc_count": len(data.get("reactions") or []),
        "preferred_term_count": pt_count,
        "brand_count": len(data.get("brands") or []),
        "file": f"drugs/{slug}.json",
    }


def ingest_capture_data(
    data: dict[str, Any],
    data_dir: Path = DEFAULT_DATA_DIR,
    *,
    slug: str | None = None,
) -> dict[str, Any]:
    """Write an in-memory capture dict into the catalog."""
    name = (data.get("drug") or {}).get("name") or data.get("query") or "drug"
    drug_slug = slug or slugify(str(name))
    dest_dir = drugs_dir(data_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    write_json(dest_dir / f"{drug_slug}.json", data)

    catalog = load_catalog(data_dir)
    drugs = [d for d in catalog.get("drugs", []) if d.get("slug") != drug_slug]
    entry = entry_from_capture(drug_slug, data)
    drugs.append(entry)
    drugs.sort(key=lambda d: str(d.get("name", "")).lower())
    catalog["version"] = 1
    catalog["drugs"] = drugs
    save_catalog(data_dir, catalog)
    return entry


def capture_and_ingest(
    query: str,
    data_dir: Path = DEFAULT_DATA_DIR,
    *,
    include_preferred_terms: bool = True,
    delay: float = 0.25,
) -> dict[str, Any]:
    """Fetch from VigiAccess and ingest into the PWA catalog."""
    from encoding_remover.client import VigiAccessClient

    with VigiAccessClient(page_delay_s=delay) as client:
        data = client.capture_drug(
            query, include_preferred_terms=include_preferred_terms
        )
    return ingest_capture_data(data, data_dir)


def ingest_capture(
    source: Path,
    data_dir: Path = DEFAULT_DATA_DIR,
    *,
    slug: str | None = None,
) -> dict[str, Any]:
    """Copy a capture JSON into data/drugs and refresh catalog.json."""
    source = source.resolve()
    if source.is_dir():
        candidate = source / "capture.json"
        if not candidate.exists():
            raise FileNotFoundError(f"No capture.json in {source}")
        source = candidate

    data = json.loads(source.read_text(encoding="utf-8"))
    return ingest_capture_data(data, data_dir, slug=slug)