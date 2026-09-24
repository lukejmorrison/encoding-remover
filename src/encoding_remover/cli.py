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
from encoding_remover.ingest import DEFAULT_DATA_DIR, ingest_capture
from encoding_remover.serve import serve as serve_app

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
    ingest: bool = typer.Option(
        False,
        "--ingest",
        help="Also copy the capture into data/ for the PWA catalog",
    ),
) -> None:
    """Search VigiAccess and export clean decoded metadata."""
    with VigiAccessClient(page_delay_s=delay) as client:
        data = client.capture_drug(
            query, include_preferred_terms=not no_preferred_terms
        )

    written_path: Path
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
        written_path = json_path
    else:
        write_json(output, data)
        typer.echo(
            f"Wrote {output} — {data['drug']['name']}: "
            f"{data['total_reports']} reports, {len(data['reactions'])} SOCs"
        )
        written_path = output

    if ingest:
        entry = ingest_capture(written_path, DEFAULT_DATA_DIR)
        typer.echo(f"Ingested → data/{entry['file']} ({entry['slug']})")


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


@app.command("ingest")
def ingest_cmd(
    source: Path = typer.Argument(
        ...,
        help="Capture JSON file or directory containing capture.json",
    ),
    data_dir: Path = typer.Option(
        DEFAULT_DATA_DIR,
        "--data-dir",
        help="Catalog root (contains catalog.json + drugs/)",
    ),
    slug: Optional[str] = typer.Option(
        None,
        "--slug",
        help="Override URL slug (default: slugified drug name)",
    ),
) -> None:
    """Add a capture file to the PWA data catalog."""
    entry = ingest_capture(source, data_dir, slug=slug)
    typer.echo(
        f"Ingested {entry['name']}: {entry['total_reports']} reports → data/{entry['file']}"
    )


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(4173, "--port"),
    no_open: bool = typer.Option(False, "--no-open", help="Do not open a browser"),
) -> None:
    """Serve the built PWA and ingested data/ directory."""
    serve_app(host=host, port=port, open_browser=not no_open)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
