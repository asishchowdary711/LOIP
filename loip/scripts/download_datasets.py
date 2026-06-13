"""Download and verify research datasets for LOIP model training.

Datasets:
  - MIDV-500/2020: OCR robustness testing (European/Russian IDs — NOT Indian doc training)
  - RVL-CDIP: LayoutLMv3 backbone pre-training (400K docs, 16 categories)
  - FUNSD: Donut backbone pre-training (199 annotated English forms)
  - DocVQA: Qwen2.5-VL validation benchmark (ANLS ≥ 0.75 gate)
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import tarfile
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import click
import requests

logger = logging.getLogger(__name__)

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB


@dataclass
class DatasetSpec:
    name: str
    url: str
    sha256: str | None
    archive_type: str  # "zip", "tar.gz", "tar", "none"
    role: str
    size_hint: str
    extract_subdir: str | None = None
    mirror_urls: list[str] = field(default_factory=list)


DATASETS: dict[str, DatasetSpec] = {
    "midv500": DatasetSpec(
        name="MIDV-500",
        url="https://ftp.smartengines.com/midv-500/dataset/midv-500.zip",
        sha256=None,
        archive_type="zip",
        role="OCR robustness testing only — European/Russian IDs, NOT Indian doc training",
        size_hint="~1.5 GB",
    ),
    "midv2020": DatasetSpec(
        name="MIDV-2020",
        url="https://ftp.smartengines.com/midv-2020/dataset/midv-2020.zip",
        sha256=None,
        archive_type="zip",
        role="OCR robustness testing — extended lighting/angle variations",
        size_hint="~4.5 GB",
    ),
    "rvlcdip": DatasetSpec(
        name="RVL-CDIP",
        url="https://huggingface.co/datasets/rvl_cdip/resolve/main/data/rvl-cdip.tar.gz",
        sha256=None,
        archive_type="tar.gz",
        role="LayoutLMv3 backbone pre-training — 400K docs, 16 categories",
        size_hint="~38 GB",
        mirror_urls=[
            "https://adamharley.com/data/rvl-cdip/rvl-cdip.tar.gz",
        ],
    ),
    "funsd": DatasetSpec(
        name="FUNSD",
        url="https://guillaumejaume.github.io/FUNSD/dataset.zip",
        sha256=None,
        archive_type="zip",
        role="Donut backbone pre-training — 199 annotated English forms",
        size_hint="~30 MB",
    ),
    "docvqa": DatasetSpec(
        name="DocVQA",
        url="https://rrc.cvc.uab.es/downloads/DocVQA.zip",
        sha256=None,
        archive_type="zip",
        role="Qwen2.5-VL validation benchmark — ANLS ≥ 0.75 gate before production",
        size_hint="~3 GB",
    ),
}


def _compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            h.update(chunk)
    return h.hexdigest()


def _download_file(url: str, dest: Path, resume: bool = True) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)

    headers = {}
    mode = "wb"
    existing_size = 0

    if resume and dest.exists():
        existing_size = dest.stat().st_size
        headers["Range"] = f"bytes={existing_size}-"
        mode = "ab"

    resp = requests.get(url, headers=headers, stream=True, timeout=60)

    if resp.status_code == 416:
        logger.info("File already fully downloaded: %s", dest.name)
        return dest

    if existing_size > 0 and resp.status_code == 206:
        logger.info("Resuming download from %d bytes", existing_size)
    elif existing_size > 0 and resp.status_code == 200:
        mode = "wb"
        existing_size = 0
        logger.info("Server doesn't support resume, re-downloading")

    resp.raise_for_status()

    total = resp.headers.get("Content-Length")
    total_size = int(total) + existing_size if total else None

    downloaded = existing_size
    with open(dest, mode) as f:
        for chunk in resp.iter_content(chunk_size=CHUNK_SIZE):
            f.write(chunk)
            downloaded += len(chunk)
            if total_size:
                pct = downloaded / total_size * 100
                print(f"\r  Downloading {dest.name}: {downloaded / 1e6:.1f} / {total_size / 1e6:.1f} MB ({pct:.0f}%)", end="", flush=True)

    if total_size:
        print()

    return dest


def _extract_archive(archive_path: Path, extract_to: Path, archive_type: str) -> Path:
    extract_to.mkdir(parents=True, exist_ok=True)

    if archive_type == "zip":
        with zipfile.ZipFile(archive_path, "r") as zf:
            zf.extractall(extract_to)
    elif archive_type in ("tar.gz", "tar"):
        mode = "r:gz" if archive_type == "tar.gz" else "r"
        with tarfile.open(archive_path, mode) as tf:
            tf.extractall(extract_to, filter="data")
    elif archive_type == "none":
        return archive_path
    else:
        raise ValueError(f"Unknown archive type: {archive_type}")

    return extract_to


def _generate_midv_report(dataset_dir: Path, dataset_name: str) -> dict:
    """Analyze MIDV dataset distribution by document nationality/type."""
    report: dict = {
        "dataset": dataset_name,
        "warning": "European/Russian ID corpus — NOT suitable for Indian document training",
        "nationalities": {},
        "doc_types": {},
        "total_images": 0,
        "capture_conditions": [],
    }

    nationality_counter: Counter = Counter()
    doc_type_counter: Counter = Counter()
    total = 0

    for img_path in dataset_dir.rglob("*.tif"):
        total += 1
        parts = img_path.relative_to(dataset_dir).parts
        if len(parts) >= 2:
            doc_category = parts[0]
            nationality_counter[doc_category] += 1
            doc_type_counter[doc_category.split("_")[0] if "_" in doc_category else doc_category] += 1

    for img_path in dataset_dir.rglob("*.jpg"):
        total += 1
        parts = img_path.relative_to(dataset_dir).parts
        if len(parts) >= 2:
            doc_category = parts[0]
            nationality_counter[doc_category] += 1

    for img_path in dataset_dir.rglob("*.png"):
        total += 1
        parts = img_path.relative_to(dataset_dir).parts
        if len(parts) >= 2:
            doc_category = parts[0]
            nationality_counter[doc_category] += 1

    report["total_images"] = total
    report["nationalities"] = dict(nationality_counter.most_common())
    report["doc_types"] = dict(doc_type_counter.most_common())

    conditions = set()
    for subdir in dataset_dir.rglob("*"):
        if subdir.is_dir():
            name_lower = subdir.name.lower()
            for cond in ["table", "hand", "keyboard", "monitor", "clutter"]:
                if cond in name_lower:
                    conditions.add(cond)
    report["capture_conditions"] = sorted(conditions)

    return report


def download_dataset(
    spec: DatasetSpec,
    data_dir: Path,
    skip_existing: bool = True,
    verify: bool = True,
) -> dict:
    """Download, verify, and extract a single dataset."""
    dataset_dir = data_dir / spec.name.lower().replace("-", "_").replace(" ", "_")
    archive_name = Path(urlparse(spec.url).path).name
    archive_path = data_dir / "archives" / archive_name
    checksum_path = archive_path.with_suffix(archive_path.suffix + ".sha256")

    result = {
        "name": spec.name,
        "role": spec.role,
        "status": "pending",
        "path": str(dataset_dir),
        "checksum_verified": False,
    }

    if skip_existing and dataset_dir.exists() and any(dataset_dir.iterdir()):
        result["status"] = "exists"
        logger.info("Dataset %s already exists at %s, skipping", spec.name, dataset_dir)
        return result

    urls_to_try = [spec.url] + spec.mirror_urls
    downloaded = False

    for url in urls_to_try:
        try:
            logger.info("Downloading %s from %s (%s)", spec.name, url, spec.size_hint)
            _download_file(url, archive_path)
            downloaded = True
            break
        except (requests.RequestException, OSError) as e:
            logger.warning("Failed to download from %s: %s", url, e)
            continue

    if not downloaded:
        result["status"] = "download_failed"
        result["error"] = f"All URLs failed for {spec.name}"
        return result

    computed_hash = _compute_sha256(archive_path)
    checksum_path.write_text(computed_hash)

    if verify and spec.sha256:
        if computed_hash != spec.sha256:
            result["status"] = "checksum_mismatch"
            result["expected_sha256"] = spec.sha256
            result["actual_sha256"] = computed_hash
            return result
        result["checksum_verified"] = True
    else:
        result["checksum_verified"] = False
        result["sha256"] = computed_hash
        logger.info("SHA256 for %s: %s (no expected hash to verify against)", spec.name, computed_hash)

    logger.info("Extracting %s...", spec.name)
    try:
        _extract_archive(archive_path, dataset_dir, spec.archive_type)
        result["status"] = "ok"
    except Exception as e:
        result["status"] = "extract_failed"
        result["error"] = str(e)
        return result

    if spec.name.startswith("MIDV"):
        report = _generate_midv_report(dataset_dir, spec.name)
        report_path = dataset_dir / "distribution_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)
        result["distribution_report"] = str(report_path)
        result["total_images"] = report["total_images"]
        result["nationalities_count"] = len(report["nationalities"])

    return result


@click.command()
@click.option("--data-dir", "-d", type=click.Path(), default="./data",
              help="Root directory for dataset storage")
@click.option("--datasets", "-s", type=str, default="all",
              help="Comma-separated dataset names or 'all' (midv500,midv2020,rvlcdip,funsd,docvqa)")
@click.option("--skip-existing/--no-skip-existing", default=True,
              help="Skip datasets that already exist on disk")
@click.option("--verify/--no-verify", default=True,
              help="Verify checksums after download")
@click.option("--dry-run", is_flag=True, default=False,
              help="Show what would be downloaded without downloading")
def main(
    data_dir: str,
    datasets: str,
    skip_existing: bool,
    verify: bool,
    dry_run: bool,
) -> None:
    """Download and verify research datasets for LOIP model training."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "archives").mkdir(exist_ok=True)

    if datasets == "all":
        selected = list(DATASETS.values())
    else:
        keys = [k.strip().lower() for k in datasets.split(",")]
        selected = []
        for k in keys:
            if k in DATASETS:
                selected.append(DATASETS[k])
            else:
                click.echo(f"Unknown dataset: {k}. Available: {', '.join(DATASETS.keys())}")
                return

    if dry_run:
        click.echo("\nDry run — would download:\n")
        for spec in selected:
            click.echo(f"  {spec.name} ({spec.size_hint})")
            click.echo(f"    URL: {spec.url}")
            click.echo(f"    Role: {spec.role}")
            click.echo()
        return

    results = []
    for spec in selected:
        click.echo(f"\n{'=' * 60}")
        click.echo(f"Dataset: {spec.name} ({spec.size_hint})")
        click.echo(f"Role: {spec.role}")
        click.echo(f"{'=' * 60}")

        result = download_dataset(spec, root, skip_existing, verify)
        results.append(result)

        if result["status"] == "ok":
            click.echo(f"  Status: OK — extracted to {result['path']}")
            if result.get("total_images"):
                click.echo(f"  Images: {result['total_images']} across {result['nationalities_count']} categories")
                click.echo(f"  Distribution report: {result['distribution_report']}")
        elif result["status"] == "exists":
            click.echo(f"  Status: Already exists, skipped")
        else:
            click.echo(f"  Status: {result['status']}")
            if "error" in result:
                click.echo(f"  Error: {result['error']}")

        if result.get("sha256"):
            click.echo(f"  SHA256: {result['sha256']}")

    manifest_path = root / "manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(results, f, indent=2)

    click.echo(f"\n{'=' * 60}")
    click.echo("Summary")
    click.echo(f"{'=' * 60}")
    ok = sum(1 for r in results if r["status"] in ("ok", "exists"))
    failed = len(results) - ok
    click.echo(f"  Downloaded: {ok}  Failed: {failed}")
    click.echo(f"  Manifest: {manifest_path}")

    if any(r["name"].startswith("MIDV") and r["status"] == "ok" for r in results):
        click.echo("\n  WARNING: MIDV datasets contain European/Russian IDs only.")
        click.echo("  They are for OCR robustness testing, NOT Indian document training.")
        click.echo("  Indian training data comes from the annotation pipeline.")


if __name__ == "__main__":
    main()
