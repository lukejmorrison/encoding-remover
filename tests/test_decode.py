"""Offline decode tests against recorded Liraglutide fixtures."""

from __future__ import annotations

from pathlib import Path

from encoding_remover.decode import (
    parse_distribution,
    parse_dotnet_datetime,
    parse_primary_term_page,
    parse_search_results,
    pick_ingredient_match,
    unpack_msgpack,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_deobfuscate_search_liraglutide():
    payload = unpack_msgpack((FIXTURES / "search_liraglutide.msgpack").read_bytes())
    matches = parse_search_results(payload)
    assert len(matches) >= 1
    names = {m["name"] for m in matches}
    assert "Liraglutide" in names
    # No replacement-character / zero-width junk in decoded names
    for m in matches:
        assert "\u200b" not in m["name"]
        assert "\ufffd" not in m["name"]
        if m["trade_name"]:
            assert "\u200b" not in m["trade_name"]

    chosen = pick_ingredient_match(matches, "Liraglutide")
    assert chosen is not None
    assert chosen["name"] == "Liraglutide"
    assert chosen["trade_name"] is None
    assert chosen["drug_id"]


def test_parse_distribution_fixture():
    payload = unpack_msgpack(
        (FIXTURES / "distribution_liraglutide.msgpack").read_bytes()
    )
    dist = parse_distribution(payload)
    assert dist["total_reports"] > 0
    assert len(dist["reactions"]) >= 1
    assert any("Gastrointestinal" in r["soc"] for r in dist["reactions"])
    assert dist["by_sex"]
    assert dist["by_year"]
    assert dist["by_continent"]
    assert dist["by_age_group"]


def test_parse_primary_term_fixture():
    payload = unpack_msgpack((FIXTURES / "primary_term_page0.msgpack").read_bytes())
    page = parse_primary_term_page(payload)
    assert page["page"] == 0
    assert page["preferred_terms"]
    assert page["preferred_terms"][0]["term"]
    assert page["preferred_terms"][0]["count"] > 0


def test_parse_dataset_date_fixture():
    payload = unpack_msgpack((FIXTURES / "dataset_date.msgpack").read_bytes())
    dt = parse_dotnet_datetime(payload)
    assert dt.year >= 2020
