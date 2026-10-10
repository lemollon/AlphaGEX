"""Portable report images: verify bytes before exposing attachments or embeds."""
from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import zipfile

from PIL import Image

DELIVERY_VERSION = "2026-10-05.2"


def inspect_png(data: bytes, chart_id: str | None = None) -> dict:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Report chart is not PNG")
    digest = hashlib.sha256(data).hexdigest()
    if chart_id is not None and digest[:32] != chart_id:
        raise ValueError("Report chart checksum mismatch")
    with Image.open(io.BytesIO(data)) as image:
        image.load()
        if image.format != "PNG" or image.width < 1000 or image.height < 600:
            raise ValueError("Report chart dimensions/format invalid")
        if image.convert("RGB").getpixel((0, 0)) != (11, 18, 32):
            raise ValueError("Report chart dark palette invalid")
        width, height = image.size
    return dict(sha256=digest, size_bytes=len(data), width=width, height=height,
                content_type="image/png", validated=True)


def chart_id_from_ref(ref: str) -> str:
    match = re.search(r"/charts/([a-f0-9]{32})\.png$", str(ref))
    if not match:
        raise ValueError("Invalid persistent report chart reference")
    return match.group(1)


def portable_pdf(images: list[dict]) -> bytes:
    pages = []
    try:
        for asset in images:
            data = base64.b64decode(asset["png_base64"], validate=True)
            inspect_png(data, asset["chart_id"])
            with Image.open(io.BytesIO(data)) as image:
                pages.append(image.convert("RGB"))
        if not pages:
            raise ValueError("No verified report images")
        output = io.BytesIO()
        pages[0].save(output, format="PDF", save_all=True,
                      append_images=pages[1:], resolution=144.0)
        return output.getvalue()
    finally:
        for page in pages:
            page.close()


def portable_zip(payload: dict, images: list[dict], html: str) -> bytes:
    output = io.BytesIO()
    manifest = dict(delivery_version=DELIVERY_VERSION,
                    report_id=payload["report_id"], generated_at=payload["generated_at"],
                    notice="Immutable observations; generating attachments does not refresh source clocks.",
                    images=[{k:v for k,v in image.items() if k != "png_base64"} for image in images])
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("report.html", html)
        archive.writestr("report.md", payload["report_markdown"])
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("charts.pdf", portable_pdf(images))
        for asset in images:
            archive.writestr(asset["filename"], base64.b64decode(asset["png_base64"], validate=True))
    return output.getvalue()
