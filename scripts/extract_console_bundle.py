"""One-shot inspector for the Claude-generated standalone Review Console.

Reads the bundler manifest + template embedded in the standalone HTML,
decompresses each manifest entry, and emits the fully rendered HTML so we
can port its structure into Jinja templates. Not shipped — kept under
scripts/ for reproducibility.
"""

import base64
import gzip
import json
import os
import re
import sys

SRC = "/Users/developer/Downloads/Projects/LOIP/LOIP Review Console (standalone).html"
OUT = "/tmp/loip_console_bundle"


def _extract_blob(html: str, mime: str) -> str:
    m = re.search(
        rf'<script[^>]+type="{re.escape(mime)}"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if not m:
        raise SystemExit(f"missing <script type=\"{mime}\">")
    return m.group(1).strip()


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)

    html = open(SRC, encoding="utf-8").read()

    manifest = json.loads(_extract_blob(html, "__bundler/manifest"))
    template = json.loads(_extract_blob(html, "__bundler/template"))
    try:
        ext_resources = json.loads(_extract_blob(html, "__bundler/ext_resources"))
    except SystemExit:
        ext_resources = []

    uuid_to_path: dict[str, str] = {}
    for uuid, entry in manifest.items():
        data = base64.b64decode(entry["data"])
        if entry.get("compressed"):
            data = gzip.decompress(data)
        ext = {
            "font/woff2": ".woff2",
            "font/woff": ".woff",
            "application/javascript": ".js",
            "text/javascript": ".js",
            "application/json": ".json",
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/svg+xml": ".svg",
        }.get(entry.get("mime", ""), ".bin")
        path = os.path.join("assets", f"{uuid}{ext}")
        with open(os.path.join(OUT, path), "wb") as fh:
            fh.write(data)
        uuid_to_path[uuid] = path

    # Substitute uuids → relative asset paths in the template
    rendered = template
    for uuid, path in uuid_to_path.items():
        rendered = rendered.replace(uuid, path)

    # Drop SRI / crossorigin to mirror the bundler loader's behaviour
    rendered = re.sub(r'\s+integrity="[^"]*"', "", rendered)
    rendered = re.sub(r'\s+crossorigin="[^"]*"', "", rendered)

    # Inject the __resources map (id → path) the React app expects
    resource_map = {e["id"]: uuid_to_path[e["uuid"]] for e in ext_resources if e["uuid"] in uuid_to_path}
    head_open = re.search(r"<head[^>]*>", rendered, re.IGNORECASE)
    if head_open:
        i = head_open.end()
        rendered = (
            rendered[:i]
            + f"<script>window.__resources = {json.dumps(resource_map)};</script>"
            + rendered[i:]
        )

    out_html = os.path.join(OUT, "index.html")
    with open(out_html, "w", encoding="utf-8") as fh:
        fh.write(rendered)

    # Manifest summary for quick eyeballing
    print(f"Wrote {out_html}")
    print(f"  assets: {len(manifest)} ({sum(1 for e in manifest.values() if e.get('compressed'))} compressed)")
    mime_counts: dict[str, int] = {}
    for entry in manifest.values():
        mime_counts[entry.get("mime", "?")] = mime_counts.get(entry.get("mime", "?"), 0) + 1
    for mime, count in sorted(mime_counts.items()):
        print(f"    {mime}: {count}")


if __name__ == "__main__":
    main()
