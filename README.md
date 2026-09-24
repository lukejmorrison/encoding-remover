# encoding-remover

Decode VigiAccess “hidden encoding” and export clean drug ADR metadata.

## What the encoding actually is

[VigiAccess](https://www.vigiaccess.org/) is an ASP.NET + Fable (F#) SPA. Its API is **not** JSON in the browser Network “Response” tab:

1. **MessagePack** — responses use `Content-Type: application/vnd.msgpack`. Binary bytes shown as text look like gibberish (`n50SAJIA…`). Pasting them into a Base64 decoder produces mojibake with drug names mixed in.
2. **Unicode obfuscation** — human-readable names (drugs, MedDRA terms) contain invisible Unicode characters (Cf/Mn). The UI hides them; raw decoded strings look polluted until those code points are stripped.
3. **Encrypted IDs** — `DrugId` / `SocId` are opaque tokens for chaining API calls. They are not presentation data and change between requests. This tool keeps them opaque and never tries to decrypt them.

```text
POST /protocol/IProtocol/search         JSON args  →  MessagePack drugs
POST /protocol/IProtocol/distribution   DrugId     →  totals + SOCs + charts
POST /protocol/IProtocol/primaryTerm    DrugId+Soc →  preferred terms (paged)
```

## Setup

```bash
cd encoding-remover
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

## Usage

Capture everything for a drug (Liraglutide example):

```bash
encoding-remover capture Liraglutide -o out/liraglutide.json
```

JSON + flat CSVs (reactions, preferred terms, year/age/sex/continent):

```bash
encoding-remover capture Liraglutide -o out/liraglutide --csv
```

Faster summary without expanding every preferred-term page:

```bash
encoding-remover capture Liraglutide -o out/liraglutide-summary.json --no-preferred-terms
```

List decoded search matches:

```bash
encoding-remover search Liraglutide
```

Decode a raw `.msgpack` blob saved from DevTools (no network):

```bash
encoding-remover decode-file tests/fixtures/search_liraglutide.msgpack -k search
encoding-remover decode-file path/to/response.msgpack -k distribution
encoding-remover decode-file path/to/response.msgpack -k primaryTerm
```

## Output fields

- `query`, `dataset_date`, `retrieved_at`, `drug`
- `total_reports`
- `brands` / `search_matches`
- `reactions[]` → `{ soc, count, preferred_terms: [{ term, count }] }`
- `by_year`, `by_age_group`, `by_sex`, `by_continent`
- `source`, `caveat`

## Tests

```bash
pytest
```

Fixtures under `tests/fixtures/` are recorded MessagePack responses for Liraglutide.

## Caveats (WHO / UMC)

VigiAccess shows **potential** side effects from VigiBase aggregates. Counts do **not** imply causality, incidence rates, or comparable safety between products. Individual case reports are not available. Use this data only as a starting point; see the [VigiAccess FAQ](https://www.vigiaccess.org/) and UMC caveat documents.

Be polite: the client inserts a short delay between `primaryTerm` page requests (`--delay`).

This project talks to the public website remoting protocol for research/decoding. For commercial product integration, consider the official [VigiAccess API](https://who-umc.org/vigibase-data-access/vigiaccess-api/) (paid / contact UMC).
