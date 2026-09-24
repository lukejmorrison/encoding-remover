"""HTTP client for VigiAccess Fable.Remoting endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import httpx

from encoding_remover.decode import (
    brands_from_matches,
    parse_distribution,
    parse_dotnet_datetime,
    parse_primary_term_page,
    parse_search_results,
    pick_ingredient_match,
    unpack_msgpack,
)

BASE_URL = "https://www.vigiaccess.org"
DEFAULT_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "x-remoting-proxy": "true",
    "Origin": BASE_URL,
    "Referer": f"{BASE_URL}/",
    "Accept": "*/*",
    "User-Agent": "encoding-remover/0.1 (+research; polite VigiAccess client)",
}

CAVEAT = (
    "VigiAccess reports potential side effects only; counts do not imply causality, "
    "incidence, or comparable safety profiles across products. Source: WHO / UMC VigiAccess."
)


class VigiAccessClient:
    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout: float = 60.0,
        page_delay_s: float = 0.3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.page_delay_s = page_delay_s
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=DEFAULT_HEADERS,
            timeout=timeout,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> VigiAccessClient:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _post(self, method: str, body: Any) -> Any:
        path = f"/protocol/IProtocol/{method}"
        resp = self._client.post(path, json=body)
        resp.raise_for_status()
        ctype = resp.headers.get("content-type", "")
        if "msgpack" not in ctype and resp.content[:1] not in (b"\x90", b"\x91", b"\x92", b"\x93", b"\x94", b"\x95", b"\x96", b"\x97", b"\x98", b"\x99", b"\x9a", b"\x9b", b"\x9c", b"\x9d", b"\x9e", b"\x9f", b"\xdc", b"\xdd"):
            # Still try msgpack; VigiAccess always returns msgpack for these routes
            pass
        return unpack_msgpack(resp.content)

    def data_set_date(self) -> datetime:
        return parse_dotnet_datetime(self._post("dataSetDate", []))

    def search(self, term: str) -> list[dict[str, Any]]:
        return parse_search_results(self._post("search", [term]))

    def distribution(self, drug_id: str) -> dict[str, Any]:
        body = [{"DrugId": {"Encrypted": drug_id}}]
        return parse_distribution(self._post("distribution", body))

    def primary_term_page(
        self, drug_id: str, soc_id: str, page: int = 0
    ) -> dict[str, Any]:
        body = [
            {
                "DrugId": {"DrugId": {"Encrypted": drug_id}},
                "SocId": {"SocId": {"Encrypted": soc_id}},
                "Page": page,
            }
        ]
        return parse_primary_term_page(self._post("primaryTerm", body))

    def all_preferred_terms(self, drug_id: str, soc_id: str) -> list[dict[str, Any]]:
        terms: list[dict[str, Any]] = []
        page = 0
        while True:
            result = self.primary_term_page(drug_id, soc_id, page)
            terms.extend(result["preferred_terms"])
            if not result["has_more"]:
                break
            page += 1
            time.sleep(self.page_delay_s)
        return terms

    def capture_drug(
        self,
        query: str,
        *,
        include_preferred_terms: bool = True,
        drug_id: str | None = None,
    ) -> dict[str, Any]:
        """Full clean capture: search → distribution → SOC preferred terms."""
        retrieved_at = datetime.now(timezone.utc).isoformat()
        dataset_date = self.data_set_date().date().isoformat()

        matches = self.search(query)
        if not matches:
            raise LookupError(f"No VigiAccess matches for {query!r}")

        chosen = None
        if drug_id:
            for m in matches:
                if m["drug_id"] == drug_id:
                    chosen = m
                    break
            if chosen is None:
                raise LookupError(f"drug_id not found in search results for {query!r}")
        else:
            chosen = pick_ingredient_match(matches, query)
            if chosen is None:
                raise LookupError(f"No VigiAccess matches for {query!r}")

        dist = self.distribution(chosen["drug_id"])
        reactions_out: list[dict[str, Any]] = []
        for soc in dist["reactions"]:
            entry: dict[str, Any] = {
                "soc": soc["soc"],
                "count": soc["count"],
            }
            if include_preferred_terms:
                entry["preferred_terms"] = self.all_preferred_terms(
                    chosen["drug_id"], soc["soc_id"]
                )
                time.sleep(self.page_delay_s)
            reactions_out.append(entry)

        return {
            "query": query,
            "dataset_date": dataset_date,
            "retrieved_at": retrieved_at,
            "drug": {
                "name": chosen["name"],
                "trade_name": chosen["trade_name"],
            },
            "total_reports": dist["total_reports"],
            "brands": brands_from_matches(matches, chosen["name"]),
            "search_matches": [
                {"name": m["name"], "trade_name": m["trade_name"]} for m in matches
            ],
            "reactions": reactions_out,
            "by_year": dist["by_year"],
            "by_age_group": dist["by_age_group"],
            "by_sex": dist["by_sex"],
            "by_continent": dist["by_continent"],
            "source": "https://www.vigiaccess.org/",
            "caveat": CAVEAT,
        }
