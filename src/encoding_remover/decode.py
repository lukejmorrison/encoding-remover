"""VigiAccess MessagePack decode + Unicode deobfuscation."""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

import msgpack

# Invisible / combining junk used by VigiAccess Obfuscated strings
_DROP_CATEGORIES = frozenset({"Cf", "Mn", "Me", "Cc", "Cs", "Co", "Cn"})

# .NET DateTime ticks epoch (year 1 CE, UTC)
_DOTNET_EPOCH = datetime(1, 1, 1, tzinfo=timezone.utc)


def deobfuscate(s: str) -> str:
    """Strip Unicode obfuscation characters from a VigiAccess string."""
    return "".join(c for c in s if unicodedata.category(c) not in _DROP_CATEGORIES)


def deobfuscate_tree(obj: Any) -> Any:
    """Recursively deobfuscate all strings in a MessagePack tree."""
    if isinstance(obj, str):
        return deobfuscate(obj)
    if isinstance(obj, list):
        return [deobfuscate_tree(x) for x in obj]
    if isinstance(obj, dict):
        return {k: deobfuscate_tree(v) for k, v in obj.items()}
    return obj


def unpack_msgpack(data: bytes) -> Any:
    """Unpack a VigiAccess MessagePack payload and deobfuscate strings."""
    raw = msgpack.unpackb(data, raw=False, strict_map_key=False)
    return deobfuscate_tree(raw)


def unwrap_encrypted(node: Any) -> str:
    """Extract opaque token from Encrypted DU: [0, [0, token]] or [0, token]."""
    if isinstance(node, str):
        return node
    if not isinstance(node, list) or not node:
        raise ValueError(f"Unexpected Encrypted node: {node!r}")
    # Tagged Encrypted: [0, inner]
    if node[0] == 0 and len(node) >= 2:
        inner = node[1]
        if isinstance(inner, str):
            return inner
        if isinstance(inner, list) and len(inner) >= 2 and isinstance(inner[1], str):
            return inner[1]
        if isinstance(inner, list) and len(inner) >= 1 and isinstance(inner[0], str):
            return inner[0]
    raise ValueError(f"Unexpected Encrypted node: {node!r}")


def unwrap_obfuscated(node: Any) -> str:
    """Extract string from Obfuscated DU: [0, text]."""
    if isinstance(node, str):
        return deobfuscate(node)
    if isinstance(node, list) and len(node) >= 2 and node[0] == 0:
        return deobfuscate(str(node[1]))
    raise ValueError(f"Unexpected Obfuscated node: {node!r}")


def unwrap_option(node: Any) -> Any | None:
    """Fable Option: [0] = None, [1, value] = Some(value)."""
    if node is None:
        return None
    if not isinstance(node, list) or not node:
        raise ValueError(f"Unexpected Option node: {node!r}")
    if node[0] == 0 and len(node) == 1:
        return None
    if node[0] == 1 and len(node) >= 2:
        return node[1]
    raise ValueError(f"Unexpected Option node: {node!r}")


def parse_dotnet_datetime(node: Any) -> datetime:
    """Parse Fable/MessagePack DateTime as [.NET ticks, kind]."""
    if isinstance(node, datetime):
        return node
    if isinstance(node, (int, float)):
        ticks = int(node)
    elif isinstance(node, list) and node:
        ticks = int(node[0])
    else:
        raise ValueError(f"Unexpected DateTime node: {node!r}")
    # .NET ticks are 100ns; Python timedelta uses microseconds
    return _DOTNET_EPOCH + timedelta(microseconds=ticks // 10)


def parse_search_results(payload: Any) -> list[dict[str, Any]]:
    """Parse search MessagePack into clean drug match dicts."""
    results: list[dict[str, Any]] = []
    for item in payload:
        drug_id_node, name_node, trade_node = item
        trade_opt = unwrap_option(trade_node)
        trade_name = unwrap_obfuscated(trade_opt) if trade_opt is not None else None
        results.append(
            {
                "drug_id": unwrap_encrypted(drug_id_node),
                "name": unwrap_obfuscated(name_node),
                "trade_name": trade_name,
            }
        )
    return results


def parse_distribution(payload: Any) -> dict[str, Any]:
    """Parse distribution MessagePack into clean metadata."""
    total, reactions, continents, ages, sexes, years = payload
    return {
        "total_reports": int(total),
        "reactions": [
            {
                "soc_id": unwrap_encrypted(r[0]),
                "soc": unwrap_obfuscated(r[1]),
                "count": int(r[2]),
            }
            for r in reactions
        ],
        "by_continent": [{"label": str(c[0]), "count": int(c[1])} for c in continents],
        "by_age_group": [{"label": str(a[0]), "count": int(a[1])} for a in ages],
        "by_sex": [{"label": str(s[0]), "count": int(s[1])} for s in sexes],
        "by_year": [{"label": str(y[0]), "count": int(y[1])} for y in years],
    }


def parse_primary_term_page(payload: Any) -> dict[str, Any]:
    """Parse primaryTerm MessagePack page."""
    pts, page, has_more = payload
    return {
        "preferred_terms": [
            {"term": unwrap_obfuscated(pt[0]), "count": int(pt[1])} for pt in pts
        ],
        "page": int(page),
        "has_more": bool(has_more),
    }


def pick_ingredient_match(
    matches: list[dict[str, Any]], query: str
) -> dict[str, Any] | None:
    """Prefer exact ingredient name with no trade name; else first exact name."""
    q = query.strip().lower()
    exact_ingredient = [
        m for m in matches if m["name"].lower() == q and m["trade_name"] is None
    ]
    if exact_ingredient:
        return exact_ingredient[0]
    exact_any = [m for m in matches if m["name"].lower() == q]
    if exact_any:
        return exact_any[0]
    return matches[0] if matches else None


def brands_from_matches(
    matches: list[dict[str, Any]], ingredient_name: str
) -> list[str]:
    """Collect trade-name labels from search hits (not other ingredient names)."""
    brands: list[str] = []
    seen: set[str] = set()
    ing = ingredient_name.lower()
    for m in matches:
        label = m.get("trade_name")
        if not label:
            continue
        key = label.lower()
        if key == ing:
            continue
        if key not in seen:
            seen.add(key)
            brands.append(label)
    return brands
