"""CLI for VigiAccess MessagePack decode and drug capture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from encoding_remover.client import VigiAccessClient
from encoding_remover.decode import (
    parse_distribution,
    parse_dotnet_datetime,
    parse_primary_term_page,
    parse_search_results,
    unpack_msgpack,
)
from encoding_remover.export import write_csv_bundle, write_json

app = typer.Typer(
    name="encoding-remover",
    help="Decode VigiAccess MessagePack payloads and capture clean drug ADR metadata.",
    no_args_is_help=True,
)


@app.command("capture")
def capture(
    query: str = typer.Argument(..., help="Drug or vaccine name, e.g. Liraglutide"),
    output: Path = typer.Option(
        Path("out/capture.json"),
        "--output",
        "-o",
        help="JSON file path, or directory when --csv is set",
    ),
    csv: bool = typer.Option(
        False,
        "--csv",
        help="Also write flat CSV tables (output treated as a directory)",
    ),
    no_preferred_terms: bool = typer.Option(
        False,
        "--no-preferred-terms",
        help="Skip paginated PT fetch under each SOC (faster summary only)",
    ),
    delay: float = typer.Option(
        0.3,
        "--delay",
        help="Seconds between primaryTerm page requests",
    ),
) -> None:
    """Search VigiAccess and export clean decoded metadata."""
    with VigiAccessClient(page_delay_s=delay) as client:
        data = client.capture_drug(
            query, include_preferred_terms=not no_preferred_terms
        )

    if csv:
        out_dir = output if output.suffix == "" or output.is_dir() else output.parent / output.stem
        if output.suffix.lower() == ".json":
            out_dir = output.parent / output.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / "capture.json"
        write_json(json_path, data)
        paths = write_csv_bundle(out_dir, data)
        typer.echo(f"Wrote {json_path}")
        for p in paths:
            typer.echo(f"Wrote {p}")
    else:
        write_json(output, data)
        typer.echo(
            f"Wrote {output} — {data['drug']['name']}: "
            f"{data['total_reports']} reports, {len(data['reactions'])} SOCs"
        )


@app.command("search")
def search(
    query: str = typer.Argument(..., help="Drug or vaccine name"),
) -> None:
    """List search matches (decoded names only)."""
    with VigiAccessClient() as client:
        matches = client.search(query)
    for m in matches:
        trade = m["trade_name"] or "-"
        typer.echo(f"{m['name']}\ttrade={trade}")


@app.command("decode-file")
def decode_file(
    path: Path = typer.Argument(..., help="Raw .msgpack file from DevTools / capture"),
    kind: Optional[str] = typer.Option(
        None,
        "--kind",
        "-k",
        help="Optional shape: search | distribution | primaryTerm | dataSetDate | raw",
    ),
) -> None:
    """Decode a saved MessagePack response to clean JSON on stdout."""
    raw = path.read_bytes()
    payload = unpack_msgpack(raw)
    kind_l = (kind or "raw").lower()
    if kind_l in ("search",):
        out = parse_search_results(payload)
    elif kind_l in ("distribution", "dist"):
        out = parse_distribution(payload)
        # Drop opaque soc_id tokens from CLI preview? Keep for completeness.
    elif kind_l in ("primaryterm", "primary_term", "pt"):
        out = parse_primary_term_page(payload)
    elif kind_l in ("datasetdate", "date", "dataset_date"):
        out = {"dataset_date": parse_dotnet_datetime(payload).isoformat()}
    else:
        out = payload
    typer.echo(json.dumps(out, indent=2, ensure_ascii=False, default=str))


def main() -> None:
    app()


if __name__ == "__main__":
    main()
