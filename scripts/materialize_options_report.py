#!/usr/bin/env python3
"""Turn verified report asset bytes into conversation files, never remote embeds.

The API's /reports/{id}/assets JSON is the input. A read-only Postgres fallback
may supply the same schema and original persisted PNG bytes. This CLI does not
send messages, place orders or refresh the market observations.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import json
import os
from pathlib import Path
import re
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "spreadworks"))
from backend.report_assets import inspect_png, portable_pdf


def atomic_write(path: Path, data: bytes):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as target:
        temp = Path(target.name)
        target.write(data)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def materialize(assets: dict, output: Path, names: list[str] | None = None) -> dict:
    if assets.get("complete") is not True or assets.get("failures"):
        raise ValueError("Persisted chart delivery incomplete: " + str(assets.get("failures")))
    report_id = str(assets.get("report_id") or "")
    if not re.fullmatch(r"[a-f0-9]{24}", report_id):
        raise ValueError("Invalid report identity")
    selected = [row for row in assets.get("images", [])
                if row.get("has_observed_data") is True
                and (names is None or row.get("name") in names)]
    if not selected:
        raise ValueError("No requested charts contain verified observations")
    if names and {row.get("name") for row in selected} != set(names):
        raise ValueError("Requested chart unavailable or lacks observed data")
    checked = []
    # Validate the whole selected batch before writing any deliverable.
    for asset in selected:
        name = asset.get("name")
        if not re.fullmatch(r"[a-z][a-z0-9_]*", str(name)):
            raise ValueError("Unsafe chart name")
        if any(row["name"] == name for row in checked):
            raise ValueError("Duplicate chart name")
        data = base64.b64decode(asset["png_base64"], validate=True)
        metadata = inspect_png(data, asset["chart_id"])
        if metadata["sha256"] != asset["sha256"] or metadata["size_bytes"] != asset["size_bytes"]:
            raise ValueError("Attachment manifest/bytes mismatch")
        checked.append(dict(asset, filename=name+".png", **metadata))
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    for asset in checked:
        path = output / asset["filename"]
        atomic_write(path, base64.b64decode(asset["png_base64"], validate=True))
        # Read back the final path: no link is emitted to absent or partial files.
        if hashlib.sha256(path.read_bytes()).hexdigest() != asset["sha256"]:
            raise ValueError("Final attachment checksum mismatch")
        asset["local_path"] = str(path)
    pdf_path = output / ("options-report-" + report_id + "-charts.pdf")
    atomic_write(pdf_path, portable_pdf(checked))
    panels = []
    for asset in checked:
        caption = f"{asset.get('data_status', 'historical').upper()} | source {asset.get('source_timestamp') or 'see chart'}"
        panels.append(f'<section><h2>{html.escape(asset["name"].replace("_"," ").title())}</h2>'
                      f'<p>{html.escape(caption)}</p><img alt="{html.escape(asset["name"])}" '
                      f'src="data:image/png;base64,{asset["png_base64"]}"></section>')
    html_path = output / ("options-report-" + report_id + "-charts.html")
    atomic_write(html_path, ('<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1">'
               '<style>body{background:#0B1220;color:#E5E7EB;font:16px system-ui;margin:20px auto;max-width:1200px}img{width:100%}p{color:#94A3B8}</style>'
               f'<h1>Options report charts</h1><p>Snapshot {html.escape(str(assets.get("generated_at")))}</p>'
               + ''.join(panels)).encode())
    result = dict(report_id=report_id, generated_at=assets.get("generated_at"),
                  complete=True, attachment_persistence_required=True,
                  images=[{k:v for k,v in row.items() if k != "png_base64"} for row in checked],
                  pdf_path=str(pdf_path), html_path=str(html_path),
                  notice="Local validation is not proof of ChatGPT attachment upload. Persist files before linking; disclose an upload failure and retain canonical PDF/report links.")
    atomic_write(output / "delivery-manifest.json", json.dumps(result, indent=2).encode())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--charts", help="Comma-separated supported panel names; omit for all supported panels")
    args = parser.parse_args()
    print(json.dumps(materialize(json.loads(args.assets_json.read_text()), args.output,
                                 args.charts.split(",") if args.charts else None)))


if __name__ == "__main__":
    main()
