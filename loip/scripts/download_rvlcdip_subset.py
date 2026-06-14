"""Download a small labeled subset of RVL-CDIP via streaming extraction.

The full RVL-CDIP archive is ~38.7GB and not feasible to store locally
(see docs/DATA_GUIDANCE_NOTES.md). This script streams the upstream
tar.gz, extracts a bounded subset of labeled .tif images per class, and
stops once a target image count or byte budget is reached — without ever
writing the full archive to disk.

The subset is for LayoutLMv3 backbone fine-tuning smoke tests (build plan
§5.2), not for training an Indian document classifier.
"""

from __future__ import annotations

import json
import logging
import tarfile
import time
from pathlib import Path

import click
import requests

logger = logging.getLogger(__name__)

TRAIN_LABELS_URL = "https://huggingface.co/datasets/aharley/rvl_cdip/resolve/main/data/train.txt"
ARCHIVE_URL = "https://huggingface.co/datasets/aharley/rvl_cdip/resolve/main/data/rvl-cdip.tar.gz"

# 16 RVL-CDIP document categories, indexed by their label integer.
CLASS_NAMES = [
    "letter", "form", "email", "handwritten", "advertisement",
    "scientific_report", "scientific_publication", "specification",
    "file_folder", "news_article", "budget", "invoice", "presentation",
    "questionnaire", "resume", "memo",
]

DEFAULT_PER_CLASS_TARGET = 20  # 20 * 16 = 320 images
DEFAULT_MAX_BYTES = 100 * 1024 * 1024  # 100 MB safety cap
DEFAULT_MAX_SECONDS = 600


def _build_label_lookup() -> dict[str, int]:
    logger.info("Downloading label index: %s", TRAIN_LABELS_URL)
    resp = requests.get(TRAIN_LABELS_URL, timeout=60)
    resp.raise_for_status()
    lookup: dict[str, int] = {}
    for line in resp.text.splitlines():
        line = line.strip()
        if not line:
            continue
        path, label = line.rsplit(" ", 1)
        lookup[path] = int(label)
    logger.info("Loaded %d labeled paths", len(lookup))
    return lookup


def download_subset(
    out_dir: Path,
    per_class_target: int = DEFAULT_PER_CLASS_TARGET,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_seconds: int = DEFAULT_MAX_SECONDS,
) -> dict:
    lookup = _build_label_lookup()

    counts = dict.fromkeys(CLASS_NAMES, 0)
    total_bytes = 0
    total_images = 0
    start = time.monotonic()

    logger.info("Streaming %s", ARCHIVE_URL)
    resp = requests.get(ARCHIVE_URL, stream=True, timeout=60)
    resp.raise_for_status()

    try:
        with tarfile.open(fileobj=resp.raw, mode="r|gz") as tf:
            for member in tf:
                if not member.isfile() or not member.name.endswith(".tif"):
                    continue

                rel_path = member.name.removeprefix("images/")
                label = lookup.get(rel_path)
                if label is None:
                    continue

                class_name = CLASS_NAMES[label]
                if counts[class_name] >= per_class_target:
                    continue

                fileobj = tf.extractfile(member)
                if fileobj is None:
                    continue
                data = fileobj.read()

                class_dir = out_dir / class_name
                class_dir.mkdir(parents=True, exist_ok=True)
                dest = class_dir / Path(rel_path).name
                dest.write_bytes(data)

                counts[class_name] += 1
                total_images += 1
                total_bytes += len(data)

                elapsed = time.monotonic() - start
                print(
                    f"\r  {total_images} images, {total_bytes / 1e6:.1f} MB, "
                    f"{elapsed:.0f}s",
                    end="", flush=True,
                )

                if all(c >= per_class_target for c in counts.values()):
                    break
                if total_bytes >= max_bytes:
                    logger.info("\nHit byte budget (%d bytes), stopping", max_bytes)
                    break
                if elapsed >= max_seconds:
                    logger.info("\nHit time budget (%ds), stopping", max_seconds)
                    break
    finally:
        resp.close()

    print()
    return {
        "total_images": total_images,
        "total_bytes": total_bytes,
        "per_class_counts": counts,
        "per_class_target": per_class_target,
    }


@click.command()
@click.option("--out-dir", "-o", type=click.Path(), default="loip/data/rvl_cdip_subset",
              help="Output directory for the subset")
@click.option("--per-class", type=int, default=DEFAULT_PER_CLASS_TARGET,
              help="Target number of images per class")
@click.option("--max-mb", type=int, default=DEFAULT_MAX_BYTES // (1024 * 1024),
              help="Safety cap on total downloaded bytes (MB)")
@click.option("--max-seconds", type=int, default=DEFAULT_MAX_SECONDS,
              help="Safety cap on streaming time (seconds)")
def main(out_dir: str, per_class: int, max_mb: int, max_seconds: int) -> None:
    """Stream a bounded, class-balanced RVL-CDIP subset without downloading the full 38.7GB archive."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)

    result = download_subset(root, per_class, max_mb * 1024 * 1024, max_seconds)

    manifest = {
        "name": "RVL-CDIP (partial subset)",
        "role": "LayoutLMv3 backbone fine-tuning smoke sample — NOT the full 400K corpus, NOT an Indian classifier",
        "source": ARCHIVE_URL,
        "status": "downloaded_partial",
        "path": str(root),
        **result,
    }
    manifest_path = root / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    click.echo(f"\nDownloaded {result['total_images']} images "
               f"({result['total_bytes'] / 1e6:.1f} MB) to {root}")
    click.echo(f"Per-class counts: {result['per_class_counts']}")
    click.echo(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
