"""Tests for catalog ingest."""

from __future__ import annotations

import json
from pathlib import Path

from encoding_remover.ingest import ingest_capture, load_catalog


def test_ingest_capture(tmp_path: Path):
    src = tmp_path / "capture.json"
    src.write_text(
        json.dumps(
            {
                "query": "DemoDrug",
                "dataset_date": "2026-01-01",
                "retrieved_at": "2026-01-02T00:00:00+00:00",
                "drug": {"name": "DemoDrug", "trade_name": None},
                "total_reports": 10,
                "brands": ["Brand A"],
                "reactions": [
                    {
                        "soc": "Gastrointestinal disorders",
                        "count": 5,
                        "preferred_terms": [{"term": "Nausea", "count": 3}],
                    }
                ],
                "by_year": [],
                "by_age_group": [],
                "by_sex": [],
                "by_continent": [],
            }
        ),
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"
    entry = ingest_capture(src, data_dir)
    assert entry["slug"] == "demodrug"
    assert entry["preferred_term_count"] == 1
    assert (data_dir / "drugs" / "demodrug.json").exists()
    catalog = load_catalog(data_dir)
    assert len(catalog["drugs"]) == 1
    assert catalog["drugs"][0]["name"] == "DemoDrug"


def test_ingest_capture_data(tmp_path: Path):
    from encoding_remover.ingest import ingest_capture_data

    data_dir = tmp_path / "data"
    entry = ingest_capture_data(
        {
            "query": "Foo",
            "drug": {"name": "Foo", "trade_name": None},
            "total_reports": 1,
            "brands": [],
            "reactions": [],
            "dataset_date": "2026-01-01",
            "retrieved_at": "2026-01-01T00:00:00+00:00",
        },
        data_dir,
    )
    assert entry["slug"] == "foo"
    assert (data_dir / "drugs" / "foo.json").exists()
